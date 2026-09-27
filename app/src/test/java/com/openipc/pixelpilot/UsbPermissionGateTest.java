package com.openipc.pixelpilot;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import java.util.Arrays;
import java.util.Collections;
import org.junit.Test;

public class UsbPermissionGateTest {
    @Test public void asksOncePerAttachment() {
        UsbPermissionGate g = new UsbPermissionGate();
        assertTrue(g.shouldAsk("/dev/bus/usb/001/002"));
        assertFalse(g.shouldAsk("/dev/bus/usb/001/002"));   // a denial must not loop on every resume
    }

    @Test public void aReplugAsksAgain() {
        UsbPermissionGate g = new UsbPermissionGate();
        g.shouldAsk("/dev/bus/usb/001/002");
        g.retainAttached(Collections.emptyList());          // unplugged
        assertTrue(g.shouldAsk("/dev/bus/usb/001/002"));
    }

    @Test public void otherAdaptersAreIndependent() {
        UsbPermissionGate g = new UsbPermissionGate();
        g.shouldAsk("/dev/bus/usb/001/002");
        g.retainAttached(Arrays.asList("/dev/bus/usb/001/002", "/dev/bus/usb/001/003"));
        assertTrue(g.shouldAsk("/dev/bus/usb/001/003"));
        assertFalse(g.shouldAsk("/dev/bus/usb/001/002"));
    }
}
