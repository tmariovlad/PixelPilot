package com.openipc.pixelpilot.stats;

import com.openipc.xr.stats.StatsSnapshot;
import com.openipc.xr.stats.StatsSource;

import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

/**
 * The Stats page's StatsSource: the air's RTP sidecar (SidecarClient → LatencyWindow), the Quest's decoded frames
 * (VideoPlayer.drainFrameTimes), the wfb link stats and RX rate (LinkWindow), the decoder fps and the IDR / freeze
 * lever counters, folded into a new StatsSnapshot every {@link #TICK_MS} over a {@code windowUs} window.
 * The XR activity creates it when the link starts, feeds onLinkStats / onDecodedFps from its existing callbacks, and
 * closes it when the link stops; snapshot() is a volatile read, safe from any thread.
 */
public final class StatsCollector implements StatsSource, AutoCloseable {
    public static final int TICK_MS = 500;   // the page refreshes at 2 Hz
    public static final long WINDOW_US = 2_000_000;
    static final int LINE_EVERY_TICKS = 4;          // a StatsLine every 2 s
    static final long VIEWED_FOR_US = 2_500_000;    // logging stays on this long after the page was last drawn

    /** What the collector pulls on each tick (VideoPlayer, WfbNgLink, XrBridge in the app; fakes in tests). */
    public interface Inputs {
        long[] drainFrameTimes();     // VideoPlayer.drainFrameTimes()

        long[] leverCounters();       // VideoPlayer.leverCounters(): IDR ok, IDR failed, frozen slices

        int[] takeRxRate();           // WfbNgLink.takeRxRate(), or null without a link

        DisplayEstimate display();    // from XrBridge.displayGrid(), or null
    }

    private final Inputs inputs;
    private final SidecarClient sidecar;
    private final ClockSync clock;
    private final LatencyWindow latency;
    private final OwdWindow owd;
    private final LinkWindow link;
    private final CounterRate idrOk, idrFailed, frozen;
    private volatile float fpsDecoded = Float.NaN;
    private volatile StatsSnapshot snapshot = StatsSnapshot.EMPTY;
    private ScheduledExecutorService ticker;
    private volatile java.util.function.Consumer<String> lineSink;
    private volatile SnapshotListener snapshotListener;
    private volatile boolean alwaysLog;
    private volatile long viewedUntilUs = Long.MIN_VALUE;
    private int ticks;

    /** {@code sidecar} may be null (tests; no air): the air segments then stay unknown. */
    public StatsCollector(Inputs inputs, SidecarClient sidecar, long windowUs) {
        this.inputs = inputs;
        this.sidecar = sidecar;
        this.clock = sidecar != null ? sidecar.clock() : new ClockSync(16);
        latency = new LatencyWindow(windowUs);
        owd = new OwdWindow(windowUs);
        link = new LinkWindow(windowUs);
        idrOk = new CounterRate(windowUs);
        idrFailed = new CounterRate(windowUs);
        frozen = new CounterRate(windowUs);
    }

    ClockSync clock() {
        return clock;
    }

    /** SidecarClient.Listener target. */
    public void onSidecarFrame(SidecarProtocol.Frame f, long questRecvUs) {
        latency.addAir(f, questRecvUs);
    }

    /** One wfb video stats window (from the activity's WfbNGStats callback: outgoing, fec_recovered, lost, ...). */
    public void onLinkStats(long nowUs, long delivered, long fecRecovered, long lost, int decErr, int rssiARaw,
                            int rssiBRaw, int snrARaw, int snrBRaw) {
        link.addStats(nowUs, delivered, fecRecovered, lost, decErr, rssiARaw, rssiBRaw, snrARaw, snrBRaw);
    }

    /** DecodingInfo.currentFPS from the activity's decoding callback. */
    public void onDecodedFps(float fps) {
        fpsDecoded = fps;
    }

    /** Gets each new snapshot on the collector's thread (the activity: HealthMonitor.onSnapshot). */
    public interface SnapshotListener {
        void onSnapshot(long questMs, StatsSnapshot snapshot);
    }

    public void setSnapshotListener(SnapshotListener listener) {
        snapshotListener = listener;
    }

    /** Where StatsLine records go (the activity: logcat, tag StatsLine.TAG). Null: none. */
    public void setLineSink(java.util.function.Consumer<String> sink) {
        lineSink = sink;
    }

    /** Log a StatsLine every 2 s regardless of the page (the slot pref), so normal flying stays quiet. */
    public void setAlwaysLog(boolean on) {
        alwaysLog = on;
    }

    /** The Stats page was just drawn: log for the next VIEWED_FOR_US. */
    public void markViewed(long nowUs) {
        viewedUntilUs = nowUs + VIEWED_FOR_US;
    }

    /** One refresh; the ticker calls it every TICK_MS, tests call it directly. */
    synchronized void tick(long nowUs) {
        for (QuestFrame q : QuestFrame.unpack(inputs.drainFrameTimes())) {
            latency.addQuest(q);
            owd.add(q);
        }
        link.addRxRate(inputs.takeRxRate());
        long[] levers = inputs.leverCounters();
        if (levers != null && levers.length >= 3) {
            idrOk.add(nowUs, levers[0]);
            idrFailed.add(nowUs, levers[1]);
            frozen.add(nowUs, levers[2]);
        }
        StatsSnapshot.Builder b = new StatsSnapshot.Builder();
        latency.fill(b, nowUs, clock, inputs.display());
        b.owd(owd.snapshot(nowUs));
        link.fill(b, nowUs);
        b.fpsDecoded(fpsDecoded).levers(idrOk.perSecond(), idrFailed.perSecond(), frozen.perSecond());
        snapshot = b.build();
        SnapshotListener l = snapshotListener;
        if (l != null) l.onSnapshot(nowUs / 1000, snapshot);
        java.util.function.Consumer<String> sink = lineSink;
        if (++ticks % LINE_EVERY_TICKS == 0 && sink != null && (alwaysLog || nowUs < viewedUntilUs)) {
            sink.accept(StatsLine.format(snapshot, nowUs / 1000));
        }
    }

    @Override
    public StatsSnapshot snapshot() {
        return snapshot;
    }

    public synchronized void start() throws java.net.SocketException {
        if (ticker != null) return;
        if (sidecar != null) sidecar.start();
        ticker = Executors.newSingleThreadScheduledExecutor(r -> {
            Thread t = new Thread(r, "stats");
            t.setDaemon(true);
            return t;
        });
        ticker.scheduleWithFixedDelay(() -> tick(SidecarClient.nowUs()), TICK_MS, TICK_MS, TimeUnit.MILLISECONDS);
    }

    @Override
    public synchronized void close() {
        if (ticker != null) ticker.shutdownNow();
        ticker = null;
        if (sidecar != null) sidecar.close();
    }
}
