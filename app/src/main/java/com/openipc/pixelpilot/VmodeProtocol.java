package com.openipc.pixelpilot;

import com.openipc.xr.PresetCatalog;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * The VMODE1 lines between the app and the air unit's preset receiver (docs/xr/presets-design.md, "Protocol"): one
 * ASCII line per UDP datagram, {@code VMODE1 <verb> key=value ...}. Builds requests and parses replies; no I/O.
 */
final class VmodeProtocol {
    static final String VERSION = "VMODE1";

    /** A parsed reply: {@code verb} plus its key=value fields. {@code seq} is -1 for the unsolicited state beacon. */
    static final class Reply {
        final String verb;
        final Map<String, String> fields;

        Reply(String verb, Map<String, String> fields) {
            this.verb = verb;
            this.fields = fields;
        }

        int seq() {
            return intField("seq", -1);
        }

        String field(String key) {
            String v = fields.get(key);
            return v == null ? "" : v;
        }

        int intField(String key, int fallback) {
            try {
                return Integer.parseInt(fields.get(key));
            } catch (RuntimeException e) {
                return fallback;
            }
        }
    }

    private VmodeProtocol() {
    }

    static String list(int seq) {
        return String.format(Locale.US, "%s list seq=%d", VERSION, seq);
    }

    /** {@code mode} null and/or {@code kbps} 0 leave that axis unchanged. */
    static String apply(int seq, String mode, int kbps, int revertS) {
        StringBuilder b = new StringBuilder(String.format(Locale.US, "%s apply seq=%d", VERSION, seq));
        if (mode != null) b.append(" preset=").append(mode);
        if (kbps > 0) b.append(" kbps=").append(kbps);
        return b.append(" revert_s=").append(revertS).toString();
    }

    static String commit(int seq, String token) {
        return String.format(Locale.US, "%s commit seq=%d token=%s", VERSION, seq, token);
    }

    static String saveDefault(int seq) {
        return String.format(Locale.US, "%s save_default seq=%d", VERSION, seq);
    }

    /** Null for anything that is not a VMODE1 line. */
    static Reply parse(String line) {
        String[] words = line.trim().split("\\s+");
        if (words.length < 2 || !VERSION.equals(words[0])) return null;
        Map<String, String> fields = new HashMap<>();
        for (int i = 2; i < words.length; i++) {
            int eq = words[i].indexOf('=');
            if (eq > 0) fields.put(words[i].substring(0, eq), words[i].substring(eq + 1));
        }
        return new Reply(words[1], fields);
    }

    /**
     * The catalog from a {@code list} reply: {@code presets=<mode>|<label>|<desc>|<fov>|<g2g>,...} and
     * {@code qualities=<kbps>|<cost ms>,...}. Malformed entries are skipped.
     */
    static PresetCatalog catalog(Reply r) {
        List<PresetCatalog.Mode> modes = new ArrayList<>();
        for (String p : items(r.field("presets"))) {
            String[] f = p.split("\\|", -1);
            if (f.length == 5 && !f[0].isEmpty()) modes.add(new PresetCatalog.Mode(f[0], f[1], f[2], f[3], f[4]));
        }
        List<PresetCatalog.Quality> qualities = new ArrayList<>();
        for (String q : items(r.field("qualities"))) {
            String[] f = q.split("\\|", -1);
            try {
                qualities.add(new PresetCatalog.Quality(Integer.parseInt(f[0]), f.length > 1 ? f[1] : "-"));
            } catch (NumberFormatException ignored) {
                // skipped
            }
        }
        return new PresetCatalog(modes, qualities, r.field("active"), r.field("default"), r.intField("kbps", 0));
    }

    private static String[] items(String s) {
        return s.isEmpty() ? new String[0] : s.split(",");
    }
}
