package com.openipc.xr;

import java.util.Arrays;

/**
 * What the stats panel shows, switched from the controllers (audit X01, native side app/xr/.../XrInput.cpp):
 * detailed (every line, the default), compact (the first {@link #COMPACT_LINES} lines: link, telemetry, video), or
 * hidden. The signal headline (NO SIGNAL, ...) is drawn by the renderer in every mode, so hiding the panel never
 * hides an alert. UI thread only.
 */
public final class PanelMode {
    public static final int COMPACT_LINES = 3;

    private boolean compact;
    private boolean hidden;

    /** Applies the press bits from {@link XrBridge#takeInputEvents()}. */
    public void apply(int events) {
        if ((events & XrBridge.INPUT_PANEL_DETAIL) != 0) {
            if (hidden) hidden = false;          // a detail press on a hidden panel brings it back first
            else compact = !compact;
        }
        if ((events & XrBridge.INPUT_PANEL_VISIBILITY) != 0) hidden = !hidden;
    }

    /** The lines to draw for the current mode ({@code lines} are ordered most important first). */
    public String[] select(String[] lines) {
        if (hidden) return new String[0];
        return compact ? Arrays.copyOf(lines, Math.min(COMPACT_LINES, lines.length)) : lines;
    }

    /** The modes by name, in the menu's order. */
    public static final java.util.List<String> NAMES =
            java.util.Collections.unmodifiableList(Arrays.asList("detailed", "compact", "hidden"));

    public String name() {
        return hidden ? "hidden" : compact ? "compact" : "detailed";
    }

    /** Sets the mode by one of {@link #NAMES}; anything else means detailed. */
    public void set(String name) {
        hidden = "hidden".equals(name);
        compact = "compact".equals(name);
    }

    public boolean compact() {
        return compact;
    }

    public boolean hidden() {
        return hidden;
    }
}
