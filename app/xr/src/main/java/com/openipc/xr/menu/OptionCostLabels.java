package com.openipc.xr.menu;

import com.openipc.xr.OptionCosts;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.function.Function;

/**
 * The menu's cost column from the one cost table ({@link OptionCosts}, res/raw/option_costs.json): decoded fps off>on
 * for a lever, a signed latency delta, the G2G range, then the table's short note. A SPECULATION entry is marked
 * "(est.)"; an option without an entry shows nothing, never a made-up number. Ranges show their rounded mean.
 */
public final class OptionCostLabels implements MenuRenderer.CostLabels {
    private final OptionCosts costs;
    /** Which table entry an item's cost is: {group, key}, or null for none (the app knows its item ids). */
    private final Function<MenuItem, String[]> entryOf;

    public OptionCostLabels(OptionCosts costs, Function<MenuItem, String[]> entryOf) {
        this.costs = costs;
        this.entryOf = entryOf;
    }

    @Override
    public String label(MenuItem item) {
        String[] gk = entryOf.apply(item);
        if (gk == null || gk[1] == null) return "";
        OptionCosts.Option o = costs.byKey(gk[0], gk[1]);
        if (o == null) return "";
        List<String> parts = new ArrayList<>();
        if (o.fpsOff.known() && o.fpsOn.known()) {
            parts.add("fps " + whole(o.fpsOff) + ">" + whole(o.fpsOn));
        } else if (o.fps.known()) {
            parts.add("fps " + whole(o.fps));
        }
        if (o.deltaMean.known()) parts.add(String.format(Locale.US, "%+.1f ms", mean(o.deltaMean)));
        if (o.g2g.known()) parts.add("G2G " + whole(o.g2g) + " ms");
        if (!o.note.isEmpty()) parts.add(o.note);
        if (parts.isEmpty()) return "";
        String s = String.join(", ", parts);
        return "SPECULATION".equals(o.tag) ? s + " (est.)" : s;
    }

    private static double mean(OptionCosts.Range r) {
        return (r.lo + r.hi) / 2.0;
    }

    private static String whole(OptionCosts.Range r) {
        return Long.toString(Math.round(mean(r)));
    }
}
