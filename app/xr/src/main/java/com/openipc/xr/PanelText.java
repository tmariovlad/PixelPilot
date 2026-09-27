package com.openipc.xr;

import java.util.ArrayList;
import java.util.List;

/** Fits the stats panel's lines to its width: empty lines are dropped, long ones end in an ellipsis. */
public final class PanelText {
    static final String ELLIPSIS = "…";

    private PanelText() {
    }

    /** @param cols characters that fit on one line (at least 1) */
    public static String[] fit(String[] lines, int cols) {
        int c = Math.max(1, cols);
        List<String> out = new ArrayList<>(lines.length);
        for (String line : lines) {
            if (line == null || line.isEmpty()) continue;
            out.add(line.length() <= c ? line : line.substring(0, c - 1) + ELLIPSIS);
        }
        return out.toArray(new String[0]);
    }
}
