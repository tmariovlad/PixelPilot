package com.openipc.pixelpilot;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Stream;
import org.junit.Test;

/**
 * Guard for the VPN start rule. Android refuses {@code startService()} while the app's uid is idle (an activity
 * created or resumed with the display off, e.g. the RTL plugged in while the Quest sleeps) and throws
 * {@code BackgroundServiceStartNotAllowedException}, which killed the app (2026-09-27). The tunnel is therefore
 * only ever bound ({@link WfbServiceControl.Binding}); binding has no such check. The framework behaviour itself
 * can only be checked on a device (replug with the display off); this test keeps the code from sliding back.
 */
public class VpnStartRuleTest {
    private static final Path SOURCES = Paths.get("src", "main", "java");
    private static final Pattern START_CALL = Pattern.compile("\\bstart(Foreground)?Service\\s*\\(");

    @Test
    public void noProductionCodeStartsAServiceDirectly() throws IOException {
        List<String> offenders = new ArrayList<>();
        try (Stream<Path> files = Files.walk(SOURCES)) {
            for (Path f : (Iterable<Path>) files.filter(p -> p.toString().endsWith(".java"))::iterator) {
                List<String> lines = Files.readAllLines(f, StandardCharsets.UTF_8);
                for (int i = 0; i < lines.size(); i++) {
                    String code = stripComment(lines.get(i));
                    Matcher m = START_CALL.matcher(code);
                    if (m.find()) offenders.add(f + ":" + (i + 1) + ": " + lines.get(i).trim());
                }
            }
        }
        assertTrue("start the VPN tunnel with WfbServiceControl.Binding, not startService: " + offenders,
                offenders.isEmpty());
    }

    @Test
    public void serviceAnswersTheBindingAction() throws IOException {
        String service = new String(Files.readAllBytes(
                SOURCES.resolve("com/openipc/pixelpilot/WfbNgVpnService.java")), StandardCharsets.UTF_8);
        assertTrue(service.contains("WfbServiceControl.ACTION_BIND_TUNNEL.equals(intent.getAction())"));
        assertEquals("com.openipc.pixelpilot.action.BIND_TUNNEL", WfbServiceControl.ACTION_BIND_TUNNEL);
    }

    /** Every other bind (the system's VpnService.SERVICE_INTERFACE) must still reach VpnService.onBind. */
    @Test
    public void systemBindingStillGoesToVpnService() throws IOException {
        String onBind = method(serviceSource(), "public IBinder onBind(Intent intent)");
        assertTrue(onBind, onBind.contains("return super.onBind(intent);"));
    }

    /** The system keeps its own binding, so ours must ask for onRebind or a second bind never restarts the tunnel. */
    @Test
    public void unbindAsksForRebindAndRebindRestartsTheTunnel() throws IOException {
        String src = serviceSource();
        String onUnbind = method(src, "public boolean onUnbind(Intent intent)");
        assertTrue(onUnbind, onUnbind.contains("stopTunnel();") && onUnbind.contains("return true;"));
        String onRebind = method(src, "public void onRebind(Intent intent)");
        assertTrue(onRebind, onRebind.contains("startTunnel();"));
    }

    /** establish() returns null when VPN permission is gone; the tunnel must stop there, not NPE on the fd. */
    @Test
    public void aNullInterfaceStopsTheTunnelStart() throws IOException {
        String start = method(serviceSource(), "private synchronized boolean startTunnel()");
        int establish = start.indexOf("vpnInterface = establishVpnInterface();");
        int check = start.indexOf("if (vpnInterface == null)");
        int threads = start.indexOf("startVpnThreads(");
        assertTrue(start, establish >= 0 && check > establish && threads > check);
    }

    private static String serviceSource() throws IOException {
        return new String(Files.readAllBytes(SOURCES.resolve("com/openipc/pixelpilot/WfbNgVpnService.java")),
                StandardCharsets.UTF_8);
    }

    /** The body of the method with this signature, up to its closing brace at 4-space indent. */
    private static String method(String src, String signature) {
        int a = src.indexOf(signature);
        assertTrue("missing: " + signature, a >= 0);
        int b = src.indexOf("\n    }", a);
        return src.substring(a, b);
    }

    /** The line without a trailing // comment; javadoc / block-comment lines (starting with * or /*) are dropped. */
    private static String stripComment(String line) {
        String t = line.trim();
        if (t.startsWith("*") || t.startsWith("/*") || t.startsWith("//")) return "";
        int c = line.indexOf("//");
        return c >= 0 ? line.substring(0, c) : line;
    }
}
