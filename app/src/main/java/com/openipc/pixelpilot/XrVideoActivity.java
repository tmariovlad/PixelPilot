package com.openipc.pixelpilot;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.view.WindowManager;

import com.openipc.mavlink.MavlinkData;
import com.openipc.mavlink.MavlinkNative;
import com.openipc.mavlink.MavlinkUpdate;
import com.openipc.videonative.DecodingInfo;
import com.openipc.videonative.IVideoParamsChanged;
import com.openipc.videonative.LatencyExperiments;
import com.openipc.videonative.VideoPlayer;
import com.openipc.wfbngrtl8812.WfbNGStats;
import com.openipc.wfbngrtl8812.WfbNGStatsChanged;
import com.openipc.wfbngrtl8812.WfbNgLink;
import com.openipc.xr.LayerLayout;
import com.openipc.xr.DebugInput;
import com.openipc.xr.PanelMode;
import com.openipc.xr.PresetMenu;
import com.openipc.xr.SignalState;
import com.openipc.xr.XrBridge;

import java.util.Locale;

/**
 * Immersive viewer: MediaCodec renders straight into a compositor-owned surface shown as a
 * head-locked layer. The OpenXR session state is the only owner of video start/stop, so the
 * decoder never writes while the session is not VISIBLE/FOCUSED.
 */
public class XrVideoActivity extends Activity implements IVideoParamsChanged, WfbNGStatsChanged,
        XrBridge.Listener, LinkStatusListener, MavlinkUpdate {
    private static final String TAG = "pixelpilot-xr";
    private static final long STATS_PERIOD_MS = 250;

    private final Handler ui = new Handler(Looper.getMainLooper());
    private LatencyExperiments experiments;
    private XrBridge xr;
    private XrStatsRenderer stats;
    private CompositorPhase phase;
    private VideoPlayer videoPlayer;
    private WfbNgLink wfbLink;
    private WfbLinkManager wfbLinkManager;
    private final WfbServiceControl.Binding vpnBinding = new WfbServiceControl.Binding();
    // Guards videoAttached: attach runs on the UI thread, detach on the XR thread (INACTIVE) or the
    // UI thread (onDestroy). VideoPlayer's surface/start/stop calls do not need the main looper.
    private final Object videoLock = new Object();
    private boolean videoAttached;
    // Set by the XR thread: true only while the session is VISIBLE/FOCUSED. A posted attach that
    // runs after the session already went INACTIVE must not attach.
    private boolean videoAllowed;
    private volatile boolean destroying;
    private volatile DecodingInfo lastDecoding;
    private volatile WfbNGStats lastLink;
    private volatile long lastLinkNs;
    private volatile String linkStatus = "";
    private MavlinkData telemetry;         // UI thread (MavlinkNative.nativeCallBack runs in the stats tick)
    private long telemetryMs;
    private volatile String udpFallback;   // non-null: no adapter, video may still arrive over Wi-Fi here
    // What the pilot is told about the video (NO SIGNAL / WRONG KEY / ...). UI thread only.
    private final SignalState signal = new SignalState();
    private boolean panelOverVideo;
    private final PanelMode panelMode = new PanelMode();   // controller-driven: detailed / compact / hidden. UI thread.        // the panel sits over the video while signal.needsAction(). UI thread.
    private volatile int videoW, videoH;
    // Presets (docs/xr/presets-design.md): the thumbstick menu and the VMODE1 session with the air unit. UI thread.
    private final PresetMenu presetMenu = new PresetMenu();
    private VmodeClient vmodeClient;
    private VmodeSession vmode;
    // Debug builds: adb broadcasts that act like controller input (DebugInput), for scripted menu tests.
    private final android.content.BroadcastReceiver debugInput = new android.content.BroadcastReceiver() {
        @Override
        public void onReceive(android.content.Context context, Intent intent) {
            XrBridge bridge = xr;
            if (bridge != null) bridge.injectInputEvents(DebugInput.bits(intent.getStringExtra(DebugInput.EXTRA)));
        }
    };
    private boolean debugInputRegistered;

    private final Runnable statsTick = new Runnable() {
        @Override
        public void run() {
            if (wfbLinkManager != null) wfbLinkManager.checkHealth(android.os.SystemClock.elapsedRealtime());
            MavlinkNative.nativeCallBack(XrVideoActivity.this);   // calls onNewMavlinkData only on new data
            // Drained once per tick: the signal state and the phase meter read the same frames.
            long[] frames = videoPlayer != null ? videoPlayer.drainFrameReadyTimes() : new long[0];
            updateSignal(frames);
            if (signal.needsAction() != panelOverVideo && xr != null) {
                panelOverVideo = signal.needsAction();
                applyLayout();                     // moves only the panel quad; nothing on the video path
            }
            XrStatsRenderer renderer = stats;
            long now = android.os.SystemClock.elapsedRealtime();
            int events = xr != null ? xr.takeInputEvents() : 0;
            panelMode.apply(presetMenu.passThrough(events));
            boolean menuWasOpen = presetMenu.isOpen();
            PresetMenu.Action action = presetMenu.update(events, now);
            if (vmode != null) {
                if (presetMenu.isOpen() && !menuWasOpen) vmode.ensureList();
                if (action != null) vmode.apply(action);
                vmode.tick(now, frames.length, videoW, videoH);
            }
            if (renderer != null) drawPanel(renderer, now);
            XrBridge bridge = xr;
            if (bridge != null && phase != null) {
                phase.tick(frames, bridge.displayGrid());
            }
            if (bridge != null && experiments.xrThreadHints && videoPlayer != null) {
                // Receiver/decoder threads are recreated with the decoder, so keep refreshing.
                bridge.hintWorkerThreads(videoPlayer.getLatencyCriticalThreadIds());
            }
            ui.postDelayed(this, STATS_PERIOD_MS);
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        experiments = LatencyExperiments.load(this);

        xr = new XrBridge(this);
        String error = xr.start(this, experiments.xrRefreshHz, experiments.xrUseTimestamps,
                experiments.xrPerfSustainedHigh, currentLayout());
        if (error != null) {
            // No silent fallback to a slower path: a measurement would not know it changed.
            Log.e(TAG, "XR unavailable: " + error);
            xr.stop();
            xr = null;
            // A Toast is invisible in an immersive session (audit X13): report it in the 2D activity instead,
            // which also skips its XR autostart so the failing start is not retried in a loop.
            startActivity(new Intent(this, VideoActivity.class)
                    .putExtra(VideoActivity.EXTRA_XR_ERROR, "XR mode unavailable: " + error));
            finish();
            return;
        }
        stats = new XrStatsRenderer(xr.statsSurface());
        phase = new CompositorPhase(experiments.xrLatchToDisplayUs, experiments.xrPhaseReport);

        videoPlayer = new VideoPlayer(this);
        videoPlayer.setIVideoParamsChanged(this);
        videoPlayer.setDecoderLevers(experiments);

        // Launched directly (Quest library) the 2D activity never ran: provide the key ourselves.
        GsKeyStore.ensureDefault(this);
        String keyProblem = GsKeyStore.problem(GsKeyStore.get(this));
        if (keyProblem != null) {
            // The native link would throw on this key and kill the app; say so in the headset instead.
            Log.e(TAG, "wfb-ng link not started: " + keyProblem);
            signal.setConfigError(keyProblem);
            linkStatus = "wfb-ng not started: import a 64-byte gs.key in the 2D screen";
            return;
        }
        GsKeyStore.copyToFiles(this);
        wfbLink = new WfbNgLink(this);
        wfbLink.SetWfbNGStatsChanged(this);
        LinkOptions.apply(this, wfbLink);
        wfbLinkManager = new WfbLinkManager(this, this, wfbLink);
        startPresets();   // only with the wfb link: the air's receiver is at the tunnel end
    }

    /**
     * Launch XR while this instance is still alive (singleInstance) arrives here, not in onCreate. XR levers changed
     * in the 2D menu meanwhile would be silently ignored (audit X04), so start over when they differ.
     */
    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        if (experiments != null && !LatencyExperiments.load(this).sameXrStart(experiments)) {
            Log.i(TAG, "XR levers changed since this XR session started: recreating it");
            recreate();
        }
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (xr == null) return;
        if (wfbLinkManager != null) {
            wfbLinkManager.register();
            wfbLinkManager.setChannel(VideoActivity.getChannel(this));
            wfbLinkManager.setBandwidth(VideoActivity.getBandwidth(this));
            wfbLinkManager.refreshAdapters();
            wfbLinkManager.startAdapters();
        }
        MavlinkNative.nativeStart(this);   // reference-counted with the 2D activity's own start/stop
        registerDebugInput();
        if (!vpnBinding.bind(this, false)) {
            onLinkStatus("VPN not granted - start PixelPilot in 2D once to allow it");
        }
        ui.post(statsTick);
    }

    @Override
    protected void onPause() {
        super.onPause();
        if (xr == null) return;
        ui.removeCallbacks(statsTick);
        if (debugInputRegistered) {
            unregisterReceiver(debugInput);
            debugInputRegistered = false;
        }
        MavlinkNative.nativeStop(this);
        if (wfbLinkManager != null) {
            wfbLinkManager.unregister();
            wfbLinkManager.stopAdapters();
        }
        vpnBinding.unbind(this);
    }

    /** The preset headline wins while a mode switch runs (the frozen picture is expected) or when the video is OK. */
    private void drawPanel(XrStatsRenderer renderer, long now) {
        String preset = vmode != null ? vmode.headline() : "";
        boolean presetFirst = !preset.isEmpty() && (vmode.switching() || !signal.needsAction());
        String[] lines = panelMode.select(statsLines());
        if (presetMenu.isOpen()) {
            String[] menu = presetMenu.lines(TelemetryLine.armed(telemetry, now - telemetryMs), now);
            String[] all = new String[menu.length + lines.length];
            System.arraycopy(menu, 0, all, 0, menu.length);
            System.arraycopy(lines, 0, all, menu.length, lines.length);
            lines = all;
        }
        if (presetFirst) renderer.draw(preset, false, lines);
        else renderer.draw(signal.message(), signal.needsAction(), lines);
    }

    /** Debuggable builds only; exported, because adb broadcasts come from the shell user. */
    private void registerDebugInput() {
        if ((getApplicationInfo().flags & android.content.pm.ApplicationInfo.FLAG_DEBUGGABLE) == 0 || debugInputRegistered) return;
        android.content.IntentFilter filter = new android.content.IntentFilter(DebugInput.ACTION);
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.TIRAMISU) {
            registerReceiver(debugInput, filter, android.content.Context.RECEIVER_EXPORTED);
        } else {
            registerReceiver(debugInput, filter);
        }
        debugInputRegistered = true;
    }

    /** One VMODE1 client per XR activity; its callbacks are handed to the UI thread. */
    private void startPresets() {
        vmode = new VmodeSession((verb, build) -> vmodeClient.request(verb, build), presetMenu::setCatalog);
        vmodeClient = new VmodeClient(VmodeClient.target(getSharedPreferences("general", MODE_PRIVATE)
                .getString(VmodeClient.PREF_TARGET, "")), new VmodeClient.Listener() {
            @Override
            public void onReply(VmodeProtocol.Reply reply) {
                ui.post(() -> {
                    if (vmode != null) vmode.onReply(reply);
                });
            }

            @Override
            public void onNoReply(String verb) {
                ui.post(() -> {
                    if (vmode != null) vmode.onNoReply(verb);
                });
            }
        }, 300, 5);
        try {
            vmodeClient.start();
            vmode.ensureList();
        } catch (java.net.SocketException e) {
            Log.w(TAG, "presets unavailable: " + e.getMessage());
            vmode = null;
        }
    }

    @Override
    protected void onDestroy() {
        destroying = true;
        ui.removeCallbacks(statsTick);
        if (vmodeClient != null) vmodeClient.close();
        vmodeClient = null;
        vmode = null;
        detachVideo();          // stop writing before the session ends (no callback round-trip)
        if (xr != null) {
            xr.stop();
            xr = null;          // late posts (ratio change, stats) see null and do nothing
        }
        stats = null;
        if (phase != null) {
            phase.close();
            phase = null;
        }
        // Each XR launch creates its own link and player; release what would otherwise keep this destroyed
        // activity reachable (the link's stats Timer thread, the player's callback). Adapters stopped in onPause.
        if (wfbLink != null) {
            wfbLink.close();
            wfbLink = null;
        }
        if (videoPlayer != null) videoPlayer.setIVideoParamsChanged(null);
        super.onDestroy();
    }

    // ---- XR session (called on the XR thread) ------------------------------------------------

    @Override
    public void onSessionEvent(XrBridge.SessionEvent event) {
        switch (event) {
            case ACTIVE:
                synchronized (videoLock) {
                    videoAllowed = true;
                }
                ui.post(this::attachVideo);
                break;
            case INACTIVE:
                // Synchronously on the XR thread: the runtime calls xrEndSession right after this
                // returns, so the decoder must have stopped writing by then. Not routed through the
                // UI thread, which may be busy (e.g. onPause joining the wfb-ng threads).
                synchronized (videoLock) {
                    videoAllowed = false;
                }
                detachVideo();
                break;
            case EXITING:
                ui.post(this::finish);
                break;
        }
    }

    private void attachVideo() {
        synchronized (videoLock) {
            if (videoAttached || !videoAllowed || destroying || xr == null) return;
            videoPlayer.addAndStartDecoderReceiver(xr.videoSurface(), 0);
            videoPlayer.start();
            videoAttached = true;
        }
        signal.reset(System.nanoTime());   // attachVideo runs on the UI thread, like the stats tick
        Log.i(TAG, "video attached to the compositor surface");
    }

    private void detachVideo() {
        synchronized (videoLock) {
            if (!videoAttached) return;
            videoPlayer.stopAndRemoveReceiverDecoder(0);
            videoAttached = false;
        }
        lastDecoding = null;               // no stale fps/resolution after a sleep/wake or reattach
        Log.i(TAG, "video detached");
    }

    private LayerLayout currentLayout() {
        return LayerLayout.compute(videoW, videoH, experiments.xrFovDeg, LayerLayout.DEFAULT_DISTANCE_M,
                experiments.xrLayerShape == LatencyExperiments.LayerShape.CYLINDER, experiments.xrFlipVertical,
                panelOverVideo);
    }

    private void applyLayout() {
        xr.setLayout(currentLayout());
    }

    // ---- callbacks from the player / link (background threads) ------------------------------

    @Override
    public void onVideoRatioChanged(int w, int h) {
        videoW = w;
        videoH = h;
        ui.post(() -> {
            if (xr != null) applyLayout();
        });
    }

    @Override
    public void onDecodingInfoChanged(DecodingInfo decodingInfo) {
        lastDecoding = decodingInfo;
    }

    @Override
    public void onWfbNgStatsChanged(WfbNGStats data) {
        lastLinkNs = System.nanoTime();
        lastLink = data;
    }

    @Override
    public void onLinkStatus(String message) {
        linkStatus = message;
    }

    @Override
    public void onNewMavlinkData(MavlinkData data) {
        telemetry = data;
        telemetryMs = android.os.SystemClock.elapsedRealtime();
    }

    @Override
    public void onUdpFallbackAddress(String udpUrl) {
        udpFallback = udpUrl;              // kept apart from linkStatus, so neither hides the other
    }

    private void updateSignal(long[] frames) {
        DecodingInfo d = lastDecoding;
        long periodNs = d != null && d.currentFPS > 1 ? (long) (1e9 / d.currentFPS) : 0;
        WfbNGStats l = lastLink;
        SignalState.Link link = l == null ? SignalState.Link.NONE
                : new SignalState.Link(l.count_p_all, l.count_p_dec_ok, l.count_p_dec_err);
        long now = System.nanoTime();
        long statsAge = l == null ? Long.MAX_VALUE : now - lastLinkNs;
        boolean adapter = wfbLink != null && wfbLink.isRunning();
        if (adapter) udpFallback = null;
        signal.update(now, frames, periodNs, adapter, link, statsAge);
    }

    private String[] statsLines() {
        XrBridge bridge = xr;
        if (bridge == null) return new String[0];
        XrBridge.Info info = bridge.info();
        DecodingInfo d = lastDecoding;
        WfbNGStats l = lastLink;
        return new String[]{
                l == null ? "link: no stats" : String.format(Locale.US,
                        "link: sig %d  pkt %d  lost %d  fec %d  bad %d  decerr %d", l.avg_rssi, l.count_p_all,
                        l.count_p_lost, l.count_p_fec_recovered, l.count_p_bad, l.count_p_dec_err),
                TelemetryLine.format(telemetry, android.os.SystemClock.elapsedRealtime() - telemetryMs),
                d == null ? "video: no decoded frames yet"
                        : String.format(Locale.US, "%dx%d  %.0f fps  %.1f Mbit/s%s", videoW, videoH, d.currentFPS,
                        d.currentKiloBitsPerSecond / 1000f, vmode != null ? vmode.videoSuffix() : ""),
                // Separate, never summed: "parse" runs from a frame's first RTP packet to the feed, so it holds the
                // frame's spread on the radio, not decoder time (docs/xr/g2g-budget.md, the Quest's "parse" time).
                d == null ? "" : String.format(Locale.US, "hw decode %.2f ms  rx+parse %.2f ms  wait %.2f ms",
                        d.avgHWDecodingTime_ms, d.avgParsingTime_ms, d.avgWaitForInputBTime_ms),
                linkStatus,
                udpFallback == null ? "" : "no adapter: video accepted at " + udpFallback,
                phase == null ? "" : phase.summaryLine(),
                String.format(Locale.US, "XR %s Hz (req %.0f)  comp GPU %s ms  drop %s",
                        num(info.refreshHz), info.requestedHz, num(info.compositorGpuMs), num(info.droppedFrames)),
                "dec: " + videoPlayer.getDecoderSummary(),
                "exp: " + experiments.summary(),
        };
    }

    private static String num(float v) {
        return v < 0 ? "n/a" : String.format(Locale.US, "%.1f", v);
    }
}
