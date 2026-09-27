package com.openipc.pixelpilot;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

import com.openipc.mavlink.MavlinkData;
import org.junit.Test;

public class TelemetryLineTest {
    /** Raw fields as mavlink.cpp fills them: mV, cA, cm + 1000 m offset, cm. */
    private static MavlinkData data(float mv, float ca, float altRaw, byte arm, byte fix, float sats, double distCm) {
        return new MavlinkData(altRaw, 0, 0, 0, mv, ca, 0, 0, 0, 0, 0, 0, distCm, sats, 0, 0, 0, arm,
                (byte) 0, fix, (byte) 0, (byte) 0, (byte) 0, "");
    }

    @Test public void unitsMatchTheTwoDOsd() {
        assertEquals(15.8, TelemetryUnits.volts(15800), 1e-9);
        assertEquals(4, TelemetryUnits.cellCount(15.8));
        assertEquals(3.95, TelemetryUnits.cellVolts(15.8), 1e-9);
        assertEquals(4.2, TelemetryUnits.amps(420), 1e-9);
        assertEquals(12.3, TelemetryUnits.altitudeM(101230), 1e-6);
        assertEquals(120, TelemetryUnits.distanceM(12000), 1e-9);
    }

    @Test public void fullLineWithGps() {
        String s = TelemetryLine.format(data(15800, 420, 101230, (byte) 1, (byte) 3, 9, 12000), 100);
        assertEquals("BAT 15.8V 3.95V/c 4.2A  ALT 12.3m  ARMED  GPS 9  HOME 120m", s);
    }

    @Test public void noGpsAndDisarmed() {
        String s = TelemetryLine.format(data(8100, 0, 100000, (byte) 0, (byte) 0, 0, 0), 100);
        assertTrue(s, s.endsWith("disarmed  no GPS"));
    }

    @Test public void staleTelemetryIsNotShownAsCurrent() {
        assertEquals("telemetry: lost 3 s ago",
                TelemetryLine.format(data(15800, 420, 101230, (byte) 1, (byte) 3, 9, 12000), 3_000));
    }

    @Test public void noTelemetryYet() {
        assertTrue(TelemetryLine.format(null, 0).startsWith("telemetry: none"));
    }
}
