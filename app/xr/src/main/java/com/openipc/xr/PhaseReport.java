package com.openipc.xr;

import java.util.Locale;

/**
 * Wire format of the compositor-phase report the headset sends to the video source, so the source
 * can steer its frame timing until frames land just before the compositor latch.
 *
 * One ASCII line per UDP datagram:
 * {@code PPXR1 seq=<n> frames=<n> wait_us=<mean wait until latch> conc=<0..1> period_us=<display period>}.
 * The receiver owns the control loop; the headset only measures.
 */
public final class PhaseReport {
    private PhaseReport() {}

    public static String datagram(long seq, PhaseMeter.Result r, long periodNs) {
        return String.format(Locale.US, "PPXR1 seq=%d frames=%d wait_us=%d conc=%.3f period_us=%d\n",
                seq, r.n, Math.round(r.meanWaitNs / 1000.0), r.concentration, Math.round(periodNs / 1000.0));
    }

    /** Where to send reports: "host:port"; null when unset or malformed (reporting off). */
    public static final class Target {
        public final String host;
        public final int port;

        private Target(String host, int port) {
            this.host = host;
            this.port = port;
        }

        public static Target parse(String value) {
            if (value == null) return null;
            int colon = value.lastIndexOf(':');
            if (colon <= 0 || colon == value.length() - 1) return null;
            try {
                int port = Integer.parseInt(value.substring(colon + 1));
                return port > 0 && port < 65536 ? new Target(value.substring(0, colon), port) : null;
            } catch (NumberFormatException e) {
                return null;
            }
        }
    }
}
