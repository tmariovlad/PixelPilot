package com.openipc.pixelpilot;

import android.util.Log;

import com.openipc.xr.PhaseMeter;
import com.openipc.xr.PhaseReport;
import com.openipc.xr.XrBridge;

import java.io.IOException;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Measures where decoded frames land relative to the compositor latch, once per stats tick, and
 * optionally reports it to the video source (which steers its frame timing; see PhaseReport).
 * Called on the UI thread; the UDP send runs on its own thread.
 */
final class CompositorPhase {
    private static final String TAG = "pixelpilot-xr";

    private final long latchToDisplayNs;
    private final PhaseReport.Target target;
    private final ExecutorService sender;
    private DatagramSocket socket;
    private long seq;
    private PhaseMeter.Result last;
    private boolean monotonic;

    CompositorPhase(int latchToDisplayUs, String reportTarget) {
        latchToDisplayNs = latchToDisplayUs * 1000L;
        target = PhaseReport.Target.parse(reportTarget);
        sender = target == null ? null : Executors.newSingleThreadExecutor();
    }

    /** One measurement over the frames decoded since the previous tick. */
    void tick(long[] frameReadyNs, XrBridge.DisplayGrid grid) {
        if (grid.periodNs <= 0 || frameReadyNs.length == 0) return;
        monotonic = grid.monotonic;
        PhaseMeter.Result r = PhaseMeter.measure(frameReadyNs, frameReadyNs.length,
                grid.displayTimeNs - latchToDisplayNs, grid.periodNs);
        last = r;
        if (sender != null && monotonic) send(PhaseReport.datagram(++seq, r, grid.periodNs));
    }

    String summaryLine() {
        PhaseMeter.Result r = last;
        if (r == null) return "phase: no frames";
        return String.format(Locale.US, "phase: wait %.2f ms  conc %.2f  n %d%s%s", r.meanWaitNs / 1e6,
                r.concentration, r.n, monotonic ? "" : "  (XrTime, not monotonic)",
                target == null ? "" : "  -> " + target.host + ":" + target.port);
    }

    void close() {
        if (sender == null) return;
        sender.execute(() -> {
            if (socket != null) socket.close();
        });
        sender.shutdown();
    }

    private void send(String line) {
        sender.execute(() -> {
            try {
                if (socket == null) socket = new DatagramSocket();
                byte[] b = line.getBytes(StandardCharsets.US_ASCII);
                socket.send(new DatagramPacket(b, b.length, InetAddress.getByName(target.host), target.port));
            } catch (IOException e) {
                Log.w(TAG, "phase report: " + e.getMessage());
            }
        });
    }
}
