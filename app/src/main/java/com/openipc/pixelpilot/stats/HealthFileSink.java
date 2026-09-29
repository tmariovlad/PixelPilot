package com.openipc.pixelpilot.stats;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;

/**
 * Appends "TAG line" to a file in the app's directory (files/ppxr_health.log), so the slot monitor can read the health
 * log at the end of a long slot even when logcat's ring buffer has rolled over (devourer logs several lines per
 * uplink frame). Rotates to ".1" when the file passes {@code maxBytes}, so it stays bounded. Never throws into the app.
 * Read it with: adb exec-out run-as com.openipc.pixelpilot.xr cat files/ppxr_health.log (and ppxr_health.log.1).
 */
public final class HealthFileSink implements HealthMonitor.Sink {
    public static final String FILE_NAME = "ppxr_health.log";
    public static final long MAX_BYTES = 1_000_000;

    private final File file;
    private final long maxBytes;
    private boolean warned;

    public HealthFileSink(File file, long maxBytes) {
        this.file = file;
        this.maxBytes = maxBytes;
    }

    @Override
    public synchronized void line(String tag, String line) {
        try {
            if (file.length() > maxBytes) {
                File old = new File(file.getPath() + ".1");
                if (old.exists() && !old.delete()) return;
                if (!file.renameTo(old)) return;
            }
            try (FileOutputStream out = new FileOutputStream(file, true)) {
                out.write((tag + " " + line + "\n").getBytes(StandardCharsets.UTF_8));
            }
        } catch (IOException | SecurityException e) {
            if (!warned) System.err.println("health log file unavailable: " + e.getMessage());
            warned = true;   // once: the logcat copy still carries every line
        }
    }
}
