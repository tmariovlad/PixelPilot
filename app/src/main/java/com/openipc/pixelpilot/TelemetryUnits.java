package com.openipc.pixelpilot;

/**
 * The one place that turns the raw MAVLink fields of {@code MavlinkData} (as filled by app/mavlink/mavlink.cpp)
 * into units, shared by the 2D OSD and the XR panel.
 */
public final class TelemetryUnits {
    private TelemetryUnits() {
    }

    /** Battery voltage in V (raw: mV). */
    public static double volts(float rawBattery) {
        return rawBattery / 1000.0;
    }

    /** Cells in series estimated from the pack voltage (a LiPo cell tops out near 4.3 V). */
    public static int cellCount(double volts) {
        return (int) (Math.floor(volts / 4.3) + 1);
    }

    /** Average cell voltage in V. */
    public static double cellVolts(double volts) {
        return volts / cellCount(volts);
    }

    /** Current in A (raw: cA). */
    public static double amps(float rawCurrent) {
        return rawCurrent / 100.0;
    }

    /** Altitude in m (raw: cm with a +1000 m offset). */
    public static double altitudeM(float rawAltitude) {
        return rawAltitude / 100.0 - 1000;
    }

    /** Distance from home in m (raw: cm). */
    public static double distanceM(double rawDistance) {
        return rawDistance / 100.0;
    }
}
