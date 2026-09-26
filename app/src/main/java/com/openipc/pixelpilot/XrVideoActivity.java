package com.openipc.pixelpilot;

import android.app.Activity;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.view.WindowManager;
import android.widget.Toast;

import com.openipc.videonative.DecodingInfo;
import com.openipc.videonative.IVideoParamsChanged;
import com.openipc.videonative.LatencyExperiments;
import com.openipc.videonative.VideoPlayer;
import com.openipc.wfbngrtl8812.WfbNGStats;
import com.openipc.wfbngrtl8812.WfbNGStatsChanged;
import com.openipc.wfbngrtl8812.WfbNgLink;
import com.openipc.xr.LayerLayout;
import com.openipc.xr.XrBridge;

import java.util.Locale;

/**
 * Immersive viewer: MediaCodec renders straight into a compositor-owned surface shown as a
 * head-locked layer. The OpenXR session state is the only owner of video start/stop, so the
 * decoder never writes while the session is not VISIBLE/FOCUSED.
 */
public class XrVideoActivity extends Activity implements IVideoParamsChanged, WfbNGStatsChanged,
        XrBridge.Listener, LinkStatusListener {
    private static final String TAG = "pixelpilot-xr";
    private static final long STATS_PERIOD_MS = 250;

    private final Handler ui = new Handler(Looper.getMainLooper());
    private LatencyExperiments experiments;
    private XrBridge xr;
    private XrStatsRenderer stats;
    private VideoPlayer videoPlayer;
    private WfbNgLink wfbLink;
    private WfbLinkManager wfbLinkManager;
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
    private volatile String linkStatus = "";
    private volatile int videoW, videoH;

    private final Runnable statsTick = new Runnable() {
        @Override
        public void run() {
            XrStatsRenderer renderer = stats;
            if (renderer != null) renderer.draw(statsLines());
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
                experiments.xrPerfSustainedHigh);
        if (error != null) {
            // No silent fallback to a slower path: a measurement would not know it changed.
            Log.e(TAG, "XR unavailable: " + error);
            Toast.makeText(this, "XR mode unavailable: " + error, Toast.LENGTH_LONG).show();
            xr.stop();
            xr = null;
            finish();
            return;
        }
        applyLayout();
        stats = new XrStatsRenderer(xr.statsSurface());

        videoPlayer = new VideoPlayer(this);
        videoPlayer.setIVideoParamsChanged(this);
        videoPlayer.setDecoderLevers(experiments);

        wfbLink = new WfbNgLink(this);
        wfbLink.SetWfbNGStatsChanged(this);
        wfbLinkManager = new WfbLinkManager(this, this, wfbLink);
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (xr == null) return;
        wfbLinkManager.register();
        wfbLinkManager.setChannel(VideoActivity.getChannel(this));
        wfbLinkManager.setBandwidth(VideoActivity.getBandwidth(this));
        wfbLinkManager.refreshAdapters();
        wfbLinkManager.startAdapters();
        if (!WfbServiceControl.startVpn(this, false)) {
            onLinkStatus("VPN not granted - start PixelPilot in 2D once to allow it");
        }
        ui.post(statsTick);
    }

    @Override
    protected void onPause() {
        super.onPause();
        if (xr == null) return;
        ui.removeCallbacks(statsTick);
        wfbLinkManager.unregister();
        wfbLinkManager.stopAdapters();
        WfbServiceControl.stopVpn(this);
    }

    @Override
    protected void onDestroy() {
        destroying = true;
        ui.removeCallbacks(statsTick);
        detachVideo();          // stop writing before the session ends (no callback round-trip)
        if (xr != null) {
            xr.stop();
            xr = null;          // late posts (ratio change, stats) see null and do nothing
        }
        stats = null;
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
        Log.i(TAG, "video attached to the compositor surface");
    }

    private void detachVideo() {
        synchronized (videoLock) {
            if (!videoAttached) return;
            videoPlayer.stopAndRemoveReceiverDecoder(0);
            videoAttached = false;
        }
        Log.i(TAG, "video detached");
    }

    private void applyLayout() {
        xr.setLayout(LayerLayout.compute(videoW, videoH, experiments.xrFovDeg, LayerLayout.DEFAULT_DISTANCE_M,
                experiments.xrLayerShape == LatencyExperiments.LayerShape.CYLINDER, experiments.xrFlipVertical));
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
        lastLink = data;
    }

    @Override
    public void onLinkStatus(String message) {
        linkStatus = message;
    }

    @Override
    public void onUdpFallbackAddress(String udpUrl) {
        linkStatus = "No adapter - push RTP to " + udpUrl;
    }

    private String[] statsLines() {
        XrBridge bridge = xr;
        if (bridge == null) return new String[0];
        XrBridge.Info info = bridge.info();
        DecodingInfo d = lastDecoding;
        WfbNGStats l = lastLink;
        return new String[]{
                String.format(Locale.US, "XR %s Hz (req %.0f)  comp GPU %s ms  drop %s",
                        num(info.refreshHz), info.requestedHz, num(info.compositorGpuMs), num(info.droppedFrames)),
                d == null ? "video: waiting for stream"
                        : String.format(Locale.US, "%dx%d  %.0f fps  %.1f Mbit/s", videoW, videoH, d.currentFPS,
                        d.currentKiloBitsPerSecond / 1000f),
                d == null ? "" : String.format(Locale.US, "decode %.2f ms  parse %.2f ms  wait %.2f ms",
                        d.avgTotalDecodingTime_ms, d.avgParsingTime_ms, d.avgWaitForInputBTime_ms),
                "dec: " + videoPlayer.getDecoderSummary(),
                "exp: " + experiments.summary(),
                l == null ? "link: no stats" : String.format(Locale.US, "link: rssi %d  lost %d  fec %d  bad %d",
                        l.avg_rssi, l.count_p_lost, l.count_p_fec_recovered, l.count_p_bad),
                linkStatus,
        };
    }

    private static String num(float v) {
        return v < 0 ? "n/a" : String.format(Locale.US, "%.1f", v);
    }
}
