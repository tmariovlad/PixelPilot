package com.openipc.pixelpilot;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import java.io.IOException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.Test;

public class OrderedShutdownTest {

    /** A TUN whose descriptor must not be touched after close(): any poll/read after close counts as EBADF. */
    private static final class FakeTun implements TunToUdpPump.Tun, java.io.Closeable {
        final AtomicBoolean closed = new AtomicBoolean();
        final AtomicInteger usedAfterClose = new AtomicInteger();
        final CountDownLatch polling = new CountDownLatch(1);

        @Override
        public boolean awaitReadable(int timeoutMs) throws IOException {
            if (closed.get()) usedAfterClose.incrementAndGet();
            polling.countDown();
            try {
                Thread.sleep(timeoutMs);  // like poll(2) on an idle tunnel: blocks the whole timeout
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
            if (closed.get()) usedAfterClose.incrementAndGet();
            return false;
        }

        @Override
        public int read(byte[] buffer) {
            if (closed.get()) usedAfterClose.incrementAndGet();
            return 0;
        }

        @Override
        public void close() {
            closed.set(true);
        }
    }

    @Test
    public void descriptorIsClosedOnlyAfterThePumpLeftPollAndRead() throws Exception {
        FakeTun tun = new FakeTun();
        AtomicBoolean running = new AtomicBoolean(true);
        Thread pump = new Thread(() -> {
            try {
                TunToUdpPump.run(tun, frame -> {}, running::get, new byte[64]);
            } catch (IOException e) {
                throw new RuntimeException(e);
            }
        });
        pump.start();
        assertTrue(tun.polling.await(2, TimeUnit.SECONDS));  // the pump is inside poll

        boolean stopped = OrderedShutdown.stop(() -> running.set(false), 2_000, tun, pump);

        assertTrue(stopped);
        assertFalse(pump.isAlive());
        assertTrue(tun.closed.get());
        assertEquals("poll/read on a closed descriptor (EBADF)", 0, tun.usedAfterClose.get());
    }

    @Test
    public void closesTheResourceEvenIfAThreadDoesNotStopInTime() throws Exception {
        CountDownLatch release = new CountDownLatch(1);
        Thread stuck = new Thread(() -> {
            try {
                release.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });
        stuck.start();
        AtomicBoolean closed = new AtomicBoolean();

        boolean stopped = OrderedShutdown.stop(() -> {}, 50, () -> closed.set(true), stuck, null);

        assertFalse(stopped);
        assertTrue(closed.get());
        release.countDown();
        stuck.join();
    }
}
