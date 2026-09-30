package com.openipc.pixelpilot;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.view.WindowManager;

import com.openipc.mavlink.MavlinkData;
import com.openipc.pixelpilot.stats.HealthFileSink;
import com.openipc.pixelpilot.stats.HealthMonitor;
import com.openipc.pixelpilot.stats.StatsCollector;
import com.openipc.pixelpilot.stats.StatsLine;
import com.openipc.pixelpilot.stats.StatsWiring;
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
import com.openipc.xr.OptionCosts;
import com.openipc.xr.PresetCatalog;
import com.openipc.xr.RefreshWatch;
import com.openipc.xr.SignalState;
import com.openipc.xr.XrBridge;
import com.openipc.xr.menu.ApplyClass;
import com.openipc.xr.menu.MenuAction;
import com.openipc.xr.menu.MenuItem;
import com.openipc.xr.menu.MenuNavigator;
import com.openipc.xr.menu.MenuRenderer;
import com.openipc.xr.menu.OptionCostLabels;
import com.openipc.xr.menu.PageSource;
import com.openipc.xr.menu.StatsPages;
import com.openipc.xr.stats.StatsSnapshot;
import com.openipc.xr.stats.StatsSource;

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
    private final RefreshWatch refreshWatch = new RefreshWatch();
    private boolean panelOverVideo;
    private final PanelMode panelMode = new PanelMode();   // controller-driven: detailed / compact / hidden. UI thread.        // the panel sits over the video while signal.needsAction(). UI thread.
    private volatile int videoW, videoH;
    /** The decoded buffer around the visible picture (onVideoCodedSizeChanged); 0 until the decoder reports it. */
    private volatile int codedW, codedH, cropLeft, cropTop;
    // The in-headset menu (docs/xr/menu-design.md), right thumbstick only, and the VMODE1 session with the air unit
    // (docs/xr/presets-design.md) behind its Air lines. UI thread.
    private static final long MENU_PERIOD_MS = 50;
    private VmodeClient vmodeClient;
    private VmodeSession vmode;
    private PresetCatalog airCatalog;
    private MenuNavigator menu;
    private MenuRenderer menuText;
    private XrMenuActions menuActions;
    private XrMenuSurfaceRenderer menuSurface;
    private boolean menuShown;
    /** The Stats pages' data (session 36's sidecar/link model); EMPTY until it is attached. */
    private volatile StatsSource statsSource;
    private StatsCollector statsCollector;   // statsSource's implementation, fed from the callbacks below
    private volatile HealthMonitor health;   // PPXR_EVENT / PPXR_HEALTH (docs/xr/health-logging.md)
    private HealthMonitor.Sink logSink;      // logcat + files/ppxr_health.log
    private final Runnable menuTick = new Runnable() {
        @Override
        public void run() {
            long now = android.os.SystemClock.elapsedRealtime();
            handleInput(now);
            if (menu != null && menu.isOpen()) ui.postDelayed(this, MENU_PERIOD_MS);
        }
    };
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
            HealthMonitor h = health;
            if (h != null) {
                long mono = monoMs();
                h.onTick(mono, signal.kind().name(), signal.needsAction(),
                        videoPlayer != null ? videoPlayer.leverCounters() : null);
                h.onAdapter(mono, wfbLink != null && wfbLink.isRunning());
            }
            if (signal.needsAction() != panelOverVideo && xr != null) {
                panelOverVideo = signal.needsAction();
                applyLayout();                     // moves only the panel quad; nothing on the video path
            }
            XrStatsRenderer renderer = stats;
            long now = android.os.SystemClock.elapsedRealtime();
            handleInput(now);
            if (vmode != null) vmode.tick(now, frames.length, videoW, videoH);
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
        startMenu();
        startHealth();
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
        startStats();     // likewise: the air's RTP sidecar is at the tunnel end
    }

    /** CLOCK_MONOTONIC ms (System.nanoTime), the clock of the Perfetto traces and of the health/stats lines. */
    private static long monoMs() {
        return System.nanoTime() / 1_000_000;
    }

    /** PPXR_EVENT / PPXR_HEALTH, always on, to logcat and files/ppxr_health.log (docs/xr/health-logging.md). */
    private void startHealth() {
        HealthFileSink file = new HealthFileSink(new java.io.File(getFilesDir(), HealthFileSink.FILE_NAME),
                HealthFileSink.MAX_BYTES);
        logSink = (tag, line) -> {
            Log.i(tag, line);
            file.line(tag, line);
        };
        health = new HealthMonitor(logSink, mono -> System.currentTimeMillis() - (monoMs() - mono));
    }

    /** The Stats pages' data (docs/xr/stats-backend.md): sidecar + decoded frames + link, a snapshot every 0.5 s. */
    private void startStats() {
        StatsCollector c = StatsWiring.create(() -> videoPlayer, () -> wfbLink, () -> xr);
        // One PPXR_STATS line every 2 s while the Stats page is open, or always with the slot pref stats_log;
        // capture it detached (scripts/quest/ab_detached.sh), parse with scripts/quest-latch/stats_log.py.
        c.setLineSink(line -> logSink.line(StatsLine.TAG, line));
        HealthMonitor h = health;
        if (h != null) c.setSnapshotListener(h::onSnapshot);
        c.setAlwaysLog(getSharedPreferences("general", MODE_PRIVATE).getBoolean("stats_log", false));
        try {
            c.start();
        } catch (java.net.SocketException e) {
            Log.e(TAG, "stats: sidecar socket failed, the air segments stay empty", e);
        }
        statsCollector = c;
        statsSource = c;
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
    protected void onStart() {
        super.onStart();
        XrPresence.onStart();   // a USB attach now leaves the adapter to this activity (UsbAttachActivity, X15)
    }

    @Override
    protected void onStop() {
        XrPresence.onStop();
        super.onStop();
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
        ui.removeCallbacks(menuTick);
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
        if (presetFirst) renderer.draw(preset, false, lines);
        else renderer.draw(signal.message(), signal.needsAction(), lines);
    }

    /** The menu layer: tree, values, costs, and what a confirmed line does (docs/xr/menu-design.md). */
    private void startMenu() {
        MenuItem tree = XrMenuTree.build();
        XrMenuModel model = new XrMenuModel(() -> experiments, () -> airCatalog, panelMode::name);
        menu = new MenuNavigator(tree, model);
        MenuRenderer.CostLabels costs = item -> "";
        try (java.io.InputStream in = getResources().openRawResource(com.openipc.xr.R.raw.option_costs)) {
            byte[] json = new byte[in.available()];
            int n = in.read(json);
            costs = new OptionCostLabels(OptionCosts.parse(new String(json, 0, Math.max(n, 0), "UTF-8")),
                    XrVideoActivity::costEntry);
        } catch (java.io.IOException | RuntimeException e) {
            Log.w(TAG, "menu cost table unavailable: " + e.getMessage());
        }
        PageSource pages = new StatsPages(() -> {
            StatsCollector c = statsCollector;
            if (c != null) c.markViewed(System.nanoTime() / 1000);   // the page is on screen: log PPXR_STATS lines
            StatsSource src = statsSource;
            return src != null ? src.snapshot() : StatsSnapshot.EMPTY;
        });
        menuText = new MenuRenderer(model, costs, pages);
        menuActions = new XrMenuActions(new MenuEffects());
        android.view.Surface s = xr.menuSurface();
        menuSurface = s != null ? new XrMenuSurfaceRenderer(s) : null;
    }

    /** The cost-table entry of a menu line: a Quest lever by its pref key, an air line by its current value. */
    private static String[] costEntry(MenuItem item) {
        if (item.apply == ApplyClass.LIVE || item.apply == ApplyClass.RELAUNCH) return new String[]{"lever", item.id};
        return null;
    }

    /** Input bits of one tick, for the stats panel's shortcuts and the menu; draws the menu while it is open. */
    private void handleInput(long now) {
        int events = xr != null ? xr.takeInputEvents() : 0;
        panelMode.apply(events);
        if (menu == null) return;
        boolean wasOpen = menu.isOpen();
        MenuAction action = menu.update(events, now);
        if (menu.isOpen() && !wasOpen) {
            if (vmode != null) vmode.ensureList();
            ui.removeCallbacks(menuTick);
            ui.postDelayed(menuTick, MENU_PERIOD_MS);
        }
        if (action != null) menuActions.run(action);
        if (menu.isOpen() != menuShown && xr != null) {
            menuShown = menu.isOpen();
            xr.setMenuVisible(menuShown);
        }
        if (menuShown && menuSurface != null) menuSurface.draw(menuText.render(menu, now));
    }

    /** What a confirmed menu line does on this activity (XrMenuActions). */
    private final class MenuEffects implements XrMenuActions.Effects {
        private android.content.SharedPreferences.Editor edit() {
            return getSharedPreferences("general", MODE_PRIVATE).edit();
        }

        @Override public void putBoolean(String k, boolean v) { edit().putBoolean(k, v).commit(); }
        @Override public void putInt(String k, int v) { edit().putInt(k, v).commit(); }
        @Override public void putFloat(String k, float v) { edit().putFloat(k, v).commit(); }
        @Override public void putString(String k, String v) { edit().putString(k, v).commit(); }
        @Override public void remove(String k) { edit().remove(k).commit(); }

        @Override
        public void applyLive() {
            experiments = LatencyExperiments.load(XrVideoActivity.this);
            if (videoPlayer != null) videoPlayer.setDecoderLevers(experiments);   // stream levers apply at the next packet
            if (xr != null) applyLayout();
        }

        @Override
        public void relaunch() {
            Log.i(TAG, "menu: relaunching XR for a start-time lever");
            ui.postDelayed(XrVideoActivity.this::recreate, 300);
        }

        @Override public void setPanelMode(String mode) { panelMode.set(mode); }

        @Override
        public void airApply(String mode, int kbps) {
            if (vmode != null) vmode.apply(mode, kbps, false);
        }

        @Override
        public void airSaveDefault() {
            if (vmode != null) vmode.apply(null, 0, true);
        }
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
        vmode = new VmodeSession((verb, build) -> vmodeClient.request(verb, build), c -> airCatalog = c);
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
        statsSource = null;
        if (statsCollector != null) statsCollector.close();
        statsCollector = null;
        health = null;
        ui.removeCallbacks(menuTick);
        menuSurface = null;
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
                if (health != null) health.onSession(monoMs(), true);
                synchronized (videoLock) {
                    videoAllowed = true;
                }
                ui.post(this::attachVideo);
                break;
            case INACTIVE:
                if (health != null) health.onSession(monoMs(), false);
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
                panelOverVideo).withBuffer(codedW, codedH, cropLeft, cropTop);
    }

    private void applyLayout() {
        xr.setLayout(currentLayout());
    }

    // ---- callbacks from the player / link (background threads) ------------------------------

    @Override
    public void onVideoCodedSizeChanged(int w, int h, int left, int top) {
        codedW = w;
        codedH = h;
        cropLeft = left;
        cropTop = top;
    }

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
        StatsCollector c = statsCollector;
        if (c != null && decodingInfo != null) c.onDecodedFps(decodingInfo.currentFPS);
    }

    @Override
    public void onWfbNgStatsChanged(WfbNGStats data) {
        lastLinkNs = System.nanoTime();
        lastLink = data;
        StatsCollector c = statsCollector;
        if (c != null && data != null) {
            c.onLinkStats(lastLinkNs / 1000, data.count_p_outgoing, data.count_p_fec_recovered, data.count_p_lost,
                    data.count_p_dec_err, data.rssi_a, data.rssi_b, data.snr_a, data.snr_b);
        }
    }

    @Override
    public void onLinkStatus(String message) {
        HealthMonitor h = health;
        if (h != null) h.onLinkStatus(monoMs(), message);
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
        boolean holding = videoPlayer != null && videoPlayer.isFrozenUntilIdr();   // a HOLD, not a stall
        signal.setSwitching(vmode != null && vmode.switching());   // a menu preset switch's gap: SWITCHING, no alarm
        signal.update(now, frames, periodNs, adapter, link, statsAge, holding);
    }

    private String[] statsLines() {
        XrBridge bridge = xr;
        if (bridge == null) return new String[0];
        XrBridge.Info info = bridge.info();
        String refreshChange = refreshWatch.onSample(info.refreshHz, info.requestedHz);
        if (refreshChange != null) Log.i(TAG, refreshChange);  // e.g. a silent thermal drop to 72 Hz
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
                String.format(Locale.US, "XR %s Hz (req %.0f)%s  comp GPU %s ms  drop %s",
                        num(info.refreshHz), info.requestedHz, RefreshWatch.hudSuffix(info.refreshHz, info.requestedHz),
                        num(info.compositorGpuMs), num(info.droppedFrames)),
                "dec: " + videoPlayer.getDecoderSummary(),
                "exp: " + experiments.summary(),
        };
    }

    private static String num(float v) {
        return v < 0 ? "n/a" : String.format(Locale.US, "%.1f", v);
    }
}
