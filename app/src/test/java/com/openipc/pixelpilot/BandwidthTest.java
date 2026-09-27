package com.openipc.pixelpilot;

import static org.junit.Assert.assertEquals;

import org.junit.Test;

public class BandwidthTest {
    @Test public void knownValuesMap() {
        assertEquals(WfbLinkManager.Bandwidth.BANDWIDTH_20, WfbLinkManager.Bandwidth.fromMhz(20));
        assertEquals(WfbLinkManager.Bandwidth.BANDWIDTH_40, WfbLinkManager.Bandwidth.fromMhz(40));
    }

    @Test public void unknownValuesFallBackTo20InsteadOfNull() {
        assertEquals(WfbLinkManager.Bandwidth.BANDWIDTH_20, WfbLinkManager.Bandwidth.fromMhz(80));
        assertEquals(WfbLinkManager.Bandwidth.BANDWIDTH_20, WfbLinkManager.Bandwidth.fromMhz(0));
    }
}
