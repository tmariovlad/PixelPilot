package com.openipc.pixelpilot;

import com.openipc.mavlink.MavlinkData;

import java.util.Locale;

/** One line of flight telemetry for the XR panel (audit X12): battery, current, altitude, arm state, GPS, home. */
final class TelemetryLine {
    /** Older telemetry than this is shown as missing, not as current values. */
    static final long STALE_MS = 2_000;

    private TelemetryLine() {
    }

    /** True only for fresh telemetry that says armed; missing or stale telemetry counts as not armed. */
    static boolean armed(MavlinkData d, long ageMs) {
        return d != null && ageMs <= STALE_MS && d.telemetryArm == 1;
    }

    /**
     * @param d     the latest MAVLink data, or null if none arrived yet
     * @param ageMs time since {@code d} arrived
     */
    static String format(MavlinkData d, long ageMs) {
        if (d == null) return "telemetry: none (MAVLink on UDP 14550)";
        if (ageMs > STALE_MS) return String.format(Locale.US, "telemetry: lost %.0f s ago", ageMs / 1000.0);
        double v = TelemetryUnits.volts(d.telemetryBattery);
        StringBuilder sb = new StringBuilder(String.format(Locale.US, "BAT %.1fV %.2fV/c %.1fA  ALT %.1fm  %s",
                v, TelemetryUnits.cellVolts(v), TelemetryUnits.amps(d.telemetryCurrent),
                TelemetryUnits.altitudeM(d.telemetryAltitude), armed(d, ageMs) ? "ARMED" : "disarmed"));
        if (d.gps_fix_type == 0) {
            sb.append("  no GPS");
        } else {
            sb.append(String.format(Locale.US, "  GPS %.0f  HOME %.0fm", d.telemetrySat,
                    TelemetryUnits.distanceM(d.telemetryDistance)));
        }
        return sb.toString();
    }
}
