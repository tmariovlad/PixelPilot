package com.openipc.xr;

import java.util.Collections;
import java.util.List;

/**
 * The presets the air unit offers, as its {@code VMODE1 list} reply described them (docs/xr/presets-design.md). The
 * air is the single source of truth for every field here, including the measured latency and field of view; the app
 * only shows them. Immutable.
 */
public final class PresetCatalog {
    /** One video mode (the MODE axis): switching it restarts the encoder. */
    public static final class Mode {
        public final String name;    // the air's id, sent back in apply
        public final String label;   // shown to the pilot
        public final String desc;    // "<WxH>@<fps>" or "<WxH>@<fps>><encode WxH>"
        public final String fov;     // sensor share in %, e.g. "99x98"
        public final String g2g;     // measured glass-to-glass range in ms, e.g. "35.3-41.6", or "-"

        public Mode(String name, String label, String desc, String fov, String g2g) {
            this.name = name;
            this.label = label;
            this.desc = desc;
            this.fov = fov;
            this.g2g = g2g;
        }

        /** The size the decoder sees: the encode size after '>' if the air scales, else the sensor size. {w, h}. */
        public int[] encodeSize() {
            String size = desc.contains(">") ? desc.substring(desc.indexOf('>') + 1) : desc.split("@")[0];
            String[] wh = size.split("x");
            try {
                return new int[]{Integer.parseInt(wh[0]), Integer.parseInt(wh[1])};
            } catch (RuntimeException e) {
                return new int[]{0, 0};
            }
        }
    }

    /** One bitrate level (the QUALITY axis): applied live. */
    public static final class Quality {
        public final int kbps;
        public final String costMs;   // estimated extra latency against the lowest level, e.g. "1.7", or "-"

        public Quality(int kbps, String costMs) {
            this.kbps = kbps;
            this.costMs = costMs;
        }
    }

    public final List<Mode> modes;
    public final List<Quality> qualities;
    public final String activeMode;
    public final String defaultMode;
    public final int requestedKbps;

    public PresetCatalog(List<Mode> modes, List<Quality> qualities, String activeMode, String defaultMode,
                         int requestedKbps) {
        this.modes = Collections.unmodifiableList(modes);
        this.qualities = Collections.unmodifiableList(qualities);
        this.activeMode = activeMode;
        this.defaultMode = defaultMode;
        this.requestedKbps = requestedKbps;
    }

    public int modeIndex(String name) {
        for (int i = 0; i < modes.size(); i++) if (modes.get(i).name.equals(name)) return i;
        return -1;
    }

    public int qualityIndex(int kbps) {
        for (int i = 0; i < qualities.size(); i++) if (qualities.get(i).kbps == kbps) return i;
        return -1;
    }

    /** A copy with another active mode and requested bitrate (after an apply or a state beacon). */
    public PresetCatalog withActive(String mode, int kbps) {
        return new PresetCatalog(modes, qualities, mode, defaultMode, kbps);
    }
}
