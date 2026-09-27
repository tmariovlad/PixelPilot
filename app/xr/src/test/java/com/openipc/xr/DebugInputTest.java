package com.openipc.xr;

import static org.junit.Assert.*;

import org.junit.Test;

public class DebugInputTest {
    @Test public void namesMapToTheControllerBits() {
        assertEquals(XrBridge.INPUT_STICK_RIGHT, DebugInput.bits("right"));
        assertEquals(XrBridge.INPUT_STICK_PRESS, DebugInput.bits("press"));
        assertEquals(XrBridge.INPUT_STICK_RELEASE, DebugInput.bits("release"));
        assertEquals(XrBridge.INPUT_PANEL_VISIBILITY, DebugInput.bits("visibility"));
    }

    @Test public void unknownNamesDoNothing() {
        assertEquals(0, DebugInput.bits("jump"));
        assertEquals(0, DebugInput.bits(null));
    }
}
