package com.openipc.pixelpilot;

import java.io.Closeable;
import java.io.IOException;

/**
 * Stops worker threads before closing the resource they read from.
 *
 * <p>Closing the TUN descriptor while a thread is still in poll/read on it made that read fail with EBADF
 * (seen on the Quest, 2026-09-27). The order here is: ask the threads to stop, wait for them to finish (the TUN
 * pump notices within one poll timeout, {@link TunToUdpPump#WAIT_MS}), and only then close the resource.
 */
final class OrderedShutdown {
    private OrderedShutdown() {}

    /**
     * Runs {@code requestStop}, joins every non-null thread within {@code timeoutMs} in total, then closes
     * {@code resource} (if non-null). Returns true if all threads finished in time; the resource is closed either
     * way, since leaking the descriptor would be worse than one late read failing.
     */
    static boolean stop(Runnable requestStop, long timeoutMs, Closeable resource, Thread... threads)
            throws IOException {
        requestStop.run();
        long deadline = System.nanoTime() + timeoutMs * 1_000_000L;
        boolean allStopped = true;
        for (Thread t : threads) {
            if (t == null) continue;
            long leftMs = Math.max(1, (deadline - System.nanoTime()) / 1_000_000L);
            try {
                t.join(leftMs);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
            allStopped &= !t.isAlive();
        }
        if (resource != null) resource.close();
        return allStopped;
    }
}
