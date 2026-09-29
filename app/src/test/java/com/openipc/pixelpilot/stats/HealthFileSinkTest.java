package com.openipc.pixelpilot.stats;

import static org.junit.Assert.*;

import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.List;

import org.junit.Test;

public class HealthFileSinkTest {
    private static File tempDir() throws Exception {
        return Files.createTempDirectory("health").toFile();
    }

    @Test public void appendsTagAndLinePerCall() throws Exception {
        File dir = tempDir();
        HealthFileSink s = new HealthFileSink(new File(dir, "ppxr_health.log"), 1_000_000);
        s.line("PPXR_EVENT", "t_mono_ms=1 code=X");
        s.line("PPXR_HEALTH", "t_mono_ms=2 code=HEALTH");
        List<String> lines = Files.readAllLines(new File(dir, "ppxr_health.log").toPath(), StandardCharsets.UTF_8);
        assertEquals(2, lines.size());
        assertEquals("PPXR_EVENT t_mono_ms=1 code=X", lines.get(0));
        assertEquals("PPXR_HEALTH t_mono_ms=2 code=HEALTH", lines.get(1));
    }

    @Test public void rotatesToDotOneWhenTheFileIsFull() throws Exception {
        File dir = tempDir();
        File log = new File(dir, "ppxr_health.log");
        HealthFileSink s = new HealthFileSink(log, 100);
        for (int i = 0; i < 10; i++) s.line("PPXR_EVENT", "t_mono_ms=" + i + " code=SOMETHING_LONGER");
        File old = new File(dir, "ppxr_health.log.1");
        assertTrue(old.exists());
        assertTrue("current file stays bounded", log.length() <= 100 + 64);
        assertTrue("the newest line is in the current file",
                new String(Files.readAllBytes(log.toPath()), StandardCharsets.UTF_8).contains("t_mono_ms=9 "));
    }

    @Test public void anUnwritableFileNeverThrows() {
        HealthFileSink s = new HealthFileSink(new File("/nonexistent-dir-for-test/x.log"), 100);
        s.line("PPXR_EVENT", "t_mono_ms=1 code=X");   // logged as a failure, not thrown into the video app
    }
}
