package com.openipc.pixelpilot.stats;

import com.openipc.xr.stats.StatsSnapshot;

import java.util.ArrayDeque;
import java.util.Arrays;
import java.util.Locale;
import java.util.function.LongUnaryOperator;

/**
 * Turns what the XR activity already knows into a log the user does not have to narrate (docs/xr/health-logging.md):
 * one PPXR_EVENT line per notable event and a PPXR_HEALTH summary every {@link #HEALTH_EVERY_MS}.
 *
 * Line format (agreed with the slot monitor, scripts/quest/slot_watch.py):
 * {@code t_mono_ms=<CLOCK_MONOTONIC ms> t_wall_ms=<epoch ms> code=<UPPER_SNAKE> level=<INFO|WARN|ALERT> k=v ...};
 * values carry no spaces.
 *
 * Inputs: {@link #onTick} from the activity's 250 ms UI tick (the signal state the pilot sees, SignalState.kind().name(),
 * and VideoPlayer.leverCounters()), {@link #onSnapshot} from StatsCollector's 0.5 s tick, and the discrete
 * {@link #onSession}, {@link #onAdapter}, {@link #onLinkStatus}. All thresholds are the constants below. Thread-safe.
 */
public final class HealthMonitor {
    public static final String EVENT_TAG = "PPXR_EVENT";
    public static final String HEALTH_TAG = "PPXR_HEALTH";

    static final long HEALTH_EVERY_MS = 10_000;
    static final long FREEZE_IDLE_END_MS = 500;       // no slice dropped for this long ends a freeze
    static final long DECODER_CAUSE_MS = 2_000;       // a stall this soon after a rebuild/switch is the decoder's
    static final long IDR_EVENT_EVERY_MS = 1_000;     // IDR requests are aggregated, at most one line per second
    static final double FPS_LOW_RATIO = 0.7;          // fps below 70 % of its 10 s median ...
    static final long FPS_LOW_FOR_MS = 2_000;         // ... for this long
    static final long FPS_MEDIAN_WINDOW_MS = 10_000;
    static final double LOSS_BURST_HOLES_PER_S = 20;  // post-FEC holes/s (StatsSnapshot, a 2 s window)

    /** Receives each finished line with its logcat tag. */
    public interface Sink {
        void line(String tag, String line);
    }

    private static final String OK = "OK";
    /** SignalState's kind for the expected gap of a menu-initiated preset switch (docs/xr/presets-design.md). */
    private static final String SWITCHING = "SWITCHING";
    // VideoPlayer.leverCounters(): [0..4] idrOk, idrFailed, frozenSlices, decoderRebuilds, codecSwitches;
    // [5..10] IdrRequester::Result counts (ok, refused, connect_timeout, reply_timeout, http_status, error);
    // [11..14] its connect race: attempts started, requests won by attempt >= 2, connect ms sum, requests connected.
    private static final int IDR_OK = 0, IDR_FAILED = 1, FROZEN = 2, REBUILDS = 3, SWITCHES = 4;
    private static final int REASON_FIRST = 6;   // [5] = ok, already counted in [0]
    private static final int ATTEMPTS = 11, WON_LATE = 12, CONNECT_MS_SUM = 13, CONNECTED = 14, N_COUNTERS = 15;
    private static final String[] REASONS = {"refused", "connect_timeout", "reply_timeout", "http_status", "error"};

    private final Sink sink;
    private final LongUnaryOperator wallFromMono;

    // counters from the previous tick
    private long[] prev;
    // signal
    private String kind = OK;
    private long lostSinceMs;
    private long switchSinceMs;
    private String lostCause = "";
    private long lastDecoderEventMs = Long.MIN_VALUE / 2;
    // freeze
    private boolean freezing;
    private long freezeStartMs, lastDropMs, freezeStartCount;
    // IDR aggregation
    private long idrOkAcc, idrFailAcc, lastIdrLineMs;
    private final long[] reasonAcc = new long[REASONS.length];
    private long attemptsAcc, wonLateAcc, connectMsAcc, connectedAcc;
    // discrete states
    private Boolean adapter;
    private long adapterGoneMs;
    private long sessionOffMs = -1;
    private String lastLinkStatus;
    // fps / loss
    private final ArrayDeque<double[]> fpsHistory = new ArrayDeque<>();   // {t, fps}
    private long fpsLowSinceMs = -1;
    private boolean fpsLowReported;
    private boolean lossBurst;
    private long lossStartMs;
    private double lossPeak;
    // health window
    private long winStartMs = -1;
    private long[] winStartCounters;
    private int winTicks, winDropTicks, winStalls;
    private double fpsSum, holesSum;
    private int fpsN, holesN;
    private StatsSnapshot latest = StatsSnapshot.EMPTY;

    public HealthMonitor(Sink sink, LongUnaryOperator wallFromMono) {
        this.sink = sink;
        this.wallFromMono = wallFromMono;
    }

    // ------------------------------------------------------------------------------------------------ inputs

    /** The UI tick: the signal kind the pilot sees, whether it needs the pilot, and VideoPlayer.leverCounters(). */
    public synchronized void onTick(long monoMs, String signalKind, boolean needsAction, long[] counters) {
        long[] now = counters(counters);
        if (prev == null) {
            prev = now;
            lastIdrLineMs = monoMs;
            winStartMs = monoMs;
            winStartCounters = now;
        }
        if (monoMs - winStartMs >= HEALTH_EVERY_MS) {
            emitHealth(monoMs, now);
        }
        long dFrozen = now[FROZEN] - prev[FROZEN];
        decoderEvents(monoMs, now);
        freeze(monoMs, dFrozen, now[FROZEN]);
        signal(monoMs, signalKind, needsAction, dFrozen);
        for (int r = 0; r < REASONS.length; r++) {
            reasonAcc[r] += Math.max(0, now[REASON_FIRST + r] - prev[REASON_FIRST + r]);
        }
        attemptsAcc += Math.max(0, now[ATTEMPTS] - prev[ATTEMPTS]);
        wonLateAcc += Math.max(0, now[WON_LATE] - prev[WON_LATE]);
        connectMsAcc += Math.max(0, now[CONNECT_MS_SUM] - prev[CONNECT_MS_SUM]);
        connectedAcc += Math.max(0, now[CONNECTED] - prev[CONNECTED]);
        idr(monoMs, now[IDR_OK] - prev[IDR_OK], now[IDR_FAILED] - prev[IDR_FAILED]);
        winTicks++;
        if (dFrozen > 0) winDropTicks++;
        prev = now;
    }

    /** StatsCollector's snapshot (fps, loss, RSSI/SNR, decode) every 0.5 s. */
    public synchronized void onSnapshot(long monoMs, StatsSnapshot s) {
        latest = s;
        if (!Double.isNaN(s.fpsDecoded)) {
            fpsSum += s.fpsDecoded;
            fpsN++;
            fps(monoMs, s.fpsDecoded);
        }
        if (!Double.isNaN(s.holesPerS)) {
            holesSum += s.holesPerS;
            holesN++;
            loss(monoMs, s.holesPerS);
        }
    }

    /** The XR session became visible/focused (true) or not (false): the headset asleep, the menu of the OS, ... */
    public synchronized void onSession(long monoMs, boolean active) {
        if (!active) {
            if (sessionOffMs < 0) sessionOffMs = monoMs;
            event(monoMs, "SESSION_INACTIVE", "ALERT", "");
        } else {
            String off = sessionOffMs >= 0 ? " off_ms=" + (monoMs - sessionOffMs) : "";
            sessionOffMs = -1;
            event(monoMs, "SESSION_ACTIVE", "INFO", off);
        }
    }

    /** The RTL adapter's presence; the first observation is a baseline. */
    public synchronized void onAdapter(long monoMs, boolean present) {
        if (adapter == null) {
            adapter = present;
            return;
        }
        if (present == adapter) return;
        adapter = present;
        if (!present) {
            adapterGoneMs = monoMs;
            event(monoMs, "ADAPTER_GONE", "ALERT", "");
        } else {
            event(monoMs, "ADAPTER_BACK", "INFO", " gone_ms=" + (monoMs - adapterGoneMs));
        }
    }

    /** WfbLinkManager's status texts ("link lost - restarting (1)", ...); a repeat of the last one is dropped. */
    public synchronized void onLinkStatus(long monoMs, String message) {
        if (message == null || message.equals(lastLinkStatus)) return;
        lastLinkStatus = message;
        event(monoMs, "LINK_STATUS", "INFO", " msg=" + message.trim().replaceAll("\\s+", "_"));
    }

    // ------------------------------------------------------------------------------------------------ detectors

    private static long[] counters(long[] c) {
        long[] out = new long[N_COUNTERS];
        if (c != null) System.arraycopy(c, 0, out, 0, Math.min(c.length, out.length));
        return out;
    }

    private void decoderEvents(long monoMs, long[] now) {
        if (now[REBUILDS] > prev[REBUILDS]) {
            lastDecoderEventMs = monoMs;
            event(monoMs, "DECODER_REBUILD", "WARN", " n=" + now[REBUILDS]);
        }
        if (now[SWITCHES] > prev[SWITCHES]) {
            lastDecoderEventMs = monoMs;
            event(monoMs, "CODEC_SWITCH", "INFO", " n=" + now[SWITCHES]);
        }
    }

    private void freeze(long monoMs, long dFrozen, long frozenTotal) {
        if (dFrozen > 0) {
            if (!freezing) {
                freezing = true;
                freezeStartMs = monoMs;
                freezeStartCount = frozenTotal - dFrozen;
                event(monoMs, "FREEZE_START", "WARN", "");
            }
            lastDropMs = monoMs;
        } else if (freezing && monoMs - lastDropMs >= FREEZE_IDLE_END_MS) {
            freezing = false;
            event(monoMs, "FREEZE_END", "INFO",
                    " dur_ms=" + (lastDropMs - freezeStartMs) + " slices=" + (frozenTotal - freezeStartCount));
        }
    }

    private String cause(long monoMs, String k, long dFrozen) {
        switch (k) {
            case "HOLD": return "freeze";
            case "NO_PACKETS": return "no_packets";
            case "NO_ADAPTER": return "no_adapter";
            case "WRONG_KEY": return "wrong_key";
            case "WAITING_FOR_VIDEO": return "waiting";
            default:
                if (dFrozen > 0 || freezing) return "freeze";
                if (monoMs - lastDecoderEventMs <= DECODER_CAUSE_MS) return "decoder";
                return "stall";
        }
    }

    private void signal(long monoMs, String k, boolean needsAction, long dFrozen) {
        if (k == null || k.equals(kind)) return;
        // A preset switch's expected gap is its own event, never a SIGNAL_LOST or a stall. If the switch ends without
        // video, what follows is judged as a new loss from OK. A switch that starts during a loss ends that loss's
        // accounting (its SIGNAL_OK never comes); the SWITCH_GAP line names it in from=.
        if (kind.equals(SWITCHING)) {
            event(monoMs, "SWITCH_END", "INFO",
                    " dur_ms=" + (monoMs - switchSinceMs) + (k.equals(OK) ? "" : " to=" + k));
            kind = OK;
            if (k.equals(OK)) return;
        }
        if (k.equals(SWITCHING)) {
            switchSinceMs = monoMs;
            event(monoMs, "SWITCH_GAP", "INFO", kind.equals(OK) ? "" : " from=" + kind);
            kind = k;
            return;
        }
        if (k.equals(OK)) {
            event(monoMs, "SIGNAL_OK", "INFO",
                    " was=" + kind + " dur_ms=" + (monoMs - lostSinceMs) + " cause=" + lostCause);
        } else {
            String from = kind.equals(OK) ? "" : " from=" + kind;
            if (kind.equals(OK)) {
                lostSinceMs = monoMs;
                winStalls++;
            }
            lostCause = cause(monoMs, k, dFrozen);
            event(monoMs, "SIGNAL_LOST", needsAction ? "ALERT" : "WARN", " to=" + k + " cause=" + lostCause + from);
        }
        kind = k;
    }

    private void idr(long monoMs, long dOk, long dFail) {
        idrOkAcc += Math.max(0, dOk);
        idrFailAcc += Math.max(0, dFail);
        if (idrOkAcc + idrFailAcc == 0 || monoMs - lastIdrLineMs < IDR_EVENT_EVERY_MS) return;
        boolean failed = idrFailAcc > 0;
        StringBuilder why = new StringBuilder();
        for (int r = 0; r < REASONS.length; r++) {
            if (reasonAcc[r] > 0) why.append(' ').append(REASONS[r]).append('=').append(reasonAcc[r]);
            reasonAcc[r] = 0;
        }
        // The handshake (a native without these counters reports none): SYNs started, requests won by a later
        // attempt than the first, and the mean connect time of the requests that connected.
        if (attemptsAcc > 0) {
            why.append(" attempts=").append(attemptsAcc).append(" late=").append(wonLateAcc);
            if (connectedAcc > 0) {
                why.append(" connected=").append(connectedAcc).append(" connect_ms=").append(connectMsAcc / connectedAcc);
            }
        }
        attemptsAcc = 0;
        wonLateAcc = 0;
        connectMsAcc = 0;
        connectedAcc = 0;
        event(monoMs, failed ? "IDR_FAILED" : "IDR", failed ? "WARN" : "INFO",
                " ok=" + idrOkAcc + " failed=" + idrFailAcc + why);
        idrOkAcc = 0;
        idrFailAcc = 0;
        lastIdrLineMs = monoMs;
    }

    private void fps(long monoMs, double fps) {
        fpsHistory.addLast(new double[]{monoMs, fps});
        while (!fpsHistory.isEmpty() && fpsHistory.peekFirst()[0] < monoMs - FPS_MEDIAN_WINDOW_MS) {
            fpsHistory.removeFirst();
        }
        double[] v = fpsHistory.stream().mapToDouble(p -> p[1]).sorted().toArray();
        double median = v.length % 2 == 1 ? v[v.length / 2] : (v[v.length / 2 - 1] + v[v.length / 2]) / 2;
        if (fps < FPS_LOW_RATIO * median) {
            if (fpsLowSinceMs < 0) fpsLowSinceMs = monoMs;
            if (!fpsLowReported && monoMs - fpsLowSinceMs >= FPS_LOW_FOR_MS) {
                fpsLowReported = true;
                event(monoMs, "FPS_LOW", "WARN", String.format(Locale.US, " fps=%.1f median=%.1f", fps, median));
            }
        } else {
            if (fpsLowReported) event(monoMs, "FPS_OK", "INFO", " dur_ms=" + (monoMs - fpsLowSinceMs));
            fpsLowReported = false;
            fpsLowSinceMs = -1;
        }
    }

    private void loss(long monoMs, double holes) {
        if (holes > LOSS_BURST_HOLES_PER_S) {
            if (!lossBurst) {
                lossBurst = true;
                lossStartMs = monoMs;
                lossPeak = holes;
                event(monoMs, "LOSS_BURST", "WARN", String.format(Locale.US, " holes=%.1f", holes));
            }
            lossPeak = Math.max(lossPeak, holes);
        } else if (lossBurst) {
            lossBurst = false;
            event(monoMs, "LOSS_END", "INFO",
                    String.format(Locale.US, " dur_ms=%d peak=%.1f", monoMs - lossStartMs, lossPeak));
        }
    }

    // ------------------------------------------------------------------------------------------------ output

    private void emitHealth(long monoMs, long[] now) {
        double winS = (monoMs - winStartMs) / 1000.0;
        StatsSnapshot s = latest;
        String body = String.format(Locale.US,
                " win_s=%d fps=%s frozen_pct=%s stalls_min=%.1f holes=%s idr_ok=%.2f idr_fail=%.2f"
                        + " rssiA=%s rssiB=%s snrA=%s snrB=%s dec_ms=%s kind=%s",
                Math.round(winS),
                fpsN == 0 ? "-" : String.format(Locale.US, "%.1f", fpsSum / fpsN),
                winTicks == 0 ? "-" : String.format(Locale.US, "%.1f", 100.0 * winDropTicks / winTicks),
                winStalls * 60.0 / winS,
                holesN == 0 ? "-" : String.format(Locale.US, "%.1f", holesSum / holesN),
                (now[IDR_OK] - winStartCounters[IDR_OK]) / winS,
                (now[IDR_FAILED] - winStartCounters[IDR_FAILED]) / winS,
                i(s.rssiADbm), i(s.rssiBDbm), i(s.snrADb), i(s.snrBDb),
                s.decode.n == 0 ? "-" : String.format(Locale.US, "%.2f", s.decode.p50Ms),
                kind);
        sink.line(HEALTH_TAG, head(monoMs, "HEALTH", "INFO") + body);
        winStartMs = monoMs;
        winStartCounters = Arrays.copyOf(now, now.length);
        winTicks = winDropTicks = winStalls = 0;
        fpsSum = holesSum = 0;
        fpsN = holesN = 0;
    }

    private static String i(int v) {
        return v == StatsSnapshot.NA ? "-" : Integer.toString(v);
    }

    private String head(long monoMs, String code, String level) {
        return "t_mono_ms=" + monoMs + " t_wall_ms=" + wallFromMono.applyAsLong(monoMs) + " code=" + code
                + " level=" + level;
    }

    private void event(long monoMs, String code, String level, String extra) {
        sink.line(EVENT_TAG, head(monoMs, code, level) + extra);
    }
}
