package com.openipc.pixelpilot;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import android.content.ServiceConnection;
import org.junit.Test;

/** Bookkeeping of the tunnel binding: an unbind is owed after every bindService call, even one that returned false. */
public class WfbServiceControlTest {

    private static final class FakeOps implements WfbServiceControl.Binding.Ops {
        boolean result;
        int binds, unbinds;

        FakeOps(boolean result) { this.result = result; }

        @Override
        public boolean bind(ServiceConnection c) {
            binds++;
            return result;
        }

        @Override
        public void unbind(ServiceConnection c) {
            unbinds++;
        }
    }

    @Test
    public void aFailedBindIsStillReleased() {
        WfbServiceControl.Binding b = new WfbServiceControl.Binding();
        FakeOps ops = new FakeOps(false);
        assertFalse(b.bind(ops));
        b.unbind(ops);
        assertEquals("Context.bindService docs: unbindService even if bindService returned false", 1, ops.unbinds);
    }

    @Test
    public void retryAfterAFailureReleasesTheFailedAttemptFirst() {
        WfbServiceControl.Binding b = new WfbServiceControl.Binding();
        FakeOps ops = new FakeOps(false);
        b.bind(ops);
        ops.result = true;
        assertTrue(b.bind(ops));
        assertEquals(2, ops.binds);
        assertEquals(1, ops.unbinds);
    }

    @Test
    public void aSuccessfulBindIsNotRepeatedAndIsReleasedOnce() {
        WfbServiceControl.Binding b = new WfbServiceControl.Binding();
        FakeOps ops = new FakeOps(true);
        assertTrue(b.bind(ops));
        assertTrue(b.bind(ops));
        b.unbind(ops);
        b.unbind(ops);
        assertEquals(1, ops.binds);
        assertEquals(1, ops.unbinds);
    }
}
