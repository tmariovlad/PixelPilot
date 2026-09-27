package com.openipc.pixelpilot;

import static org.junit.Assert.*;
import org.junit.Test;

public class GsKeyStoreTest {
    @Test public void sixtyFourBytesIsValid() {
        assertNull(GsKeyStore.problem(new byte[64]));
    }

    @Test public void shortOrLongKeysAreRejected() {
        assertEquals("gs.key 32 B, needs 64", GsKeyStore.problem(new byte[32]));
        assertNotNull(GsKeyStore.problem(new byte[65]));
    }

    @Test public void missingKeyIsRejected() {
        assertEquals("no gs.key", GsKeyStore.problem(new byte[0]));
        assertEquals("no gs.key", GsKeyStore.problem(null));
    }
}
