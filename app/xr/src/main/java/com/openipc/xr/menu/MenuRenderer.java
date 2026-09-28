package com.openipc.xr.menu;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

/**
 * The menu layer's text (docs/xr/menu-design.md §5): a breadcrumb title, one line per item of the current folder
 * ({@code > label  value  tag  cost}), and a hint line (a hold bar, the navigator's hint, or the controls). On a stats
 * page, the page's lines from its {@link PageSource}. Pure; every line fits {@link #COLUMNS}.
 */
public final class MenuRenderer {
    /** Columns of 28 px monospace on the 1024 px menu layer. */
    public static final int COLUMNS = 56;
    static final int LABEL = 18, VALUE = 12, TAG = 4, BAR = 10;
    static final String CONTROLS = "up/down move  right select  left back";
    static final String PAGE_FOOTER = "left: back";

    /** The cost text of an option ("" if none measured), from the one cost table. */
    public interface CostLabels {
        String label(MenuItem item);
    }

    private final MenuModel model;
    private final CostLabels costs;
    private final PageSource pages;

    public MenuRenderer(MenuModel model, CostLabels costs, PageSource pages) {
        this.model = model;
        this.costs = costs;
        this.pages = pages;
    }

    public List<MenuLine> render(MenuNavigator nav, long nowMs) {
        List<MenuLine> out = new ArrayList<>();
        out.add(new MenuLine(title(nav), MenuLine.Style.TITLE));
        MenuItem page = nav.page();
        if (page.kind == MenuItem.Kind.PAGE) {
            for (String s : pages.lines(page.id)) out.add(new MenuLine(fit(s), MenuLine.Style.NORMAL));
            out.add(new MenuLine(PAGE_FOOTER, MenuLine.Style.HINT));
            return out;
        }
        MenuItem hi = nav.highlighted();
        for (MenuItem c : page.children) out.add(line(c, c == hi, nav));
        out.add(new MenuLine(fit(hint(nav, hi, nowMs)), MenuLine.Style.HINT));
        return out;
    }

    private static String title(MenuNavigator nav) {
        StringBuilder b = new StringBuilder("MENU");
        List<MenuItem> path = nav.path();
        for (int i = 1; i < path.size(); i++) b.append(" > ").append(path.get(i).label);
        return fit(b.toString());
    }

    private MenuLine line(MenuItem c, boolean highlighted, MenuNavigator nav) {
        boolean available = model.available(c.id);
        String value = highlighted && nav.isEditing() ? "<" + format(c, nav.pendingValue()) + ">"
                : format(c, model.value(c.id));
        String cost = available ? costs.label(c) : (c.apply.isAir() ? "needs air" : "unavailable");
        String text = (highlighted ? "> " : "  ") + pad(c.label, LABEL) + pad(value, VALUE)
                + pad(c.apply.tag.isEmpty() ? "" : " " + c.apply.tag, TAG) + (cost == null ? "" : cost);
        MenuLine.Style style = !available ? MenuLine.Style.DISABLED
                : highlighted ? MenuLine.Style.HIGHLIGHT : MenuLine.Style.NORMAL;
        return new MenuLine(fit(rtrim(text)), style);
    }

    private static String format(MenuItem c, String v) {
        switch (c.kind) {
            case FOLDER:
            case PAGE:
                return ">";
            case ACTION:
                return "";
            case BOOL:
                return v == null ? "-" : "true".equals(v) ? "ON" : "OFF";
            case NUMBER:
                return v == null ? "-" : v + (c.unit.isEmpty() ? "" : " " + c.unit);
            default:
                return v == null ? "-" : v;
        }
    }

    private static String hint(MenuNavigator nav, MenuItem hi, long nowMs) {
        boolean saveHold = !nav.isEditing() && hi.isOption() && hi.apply.isAir();
        long total = saveHold ? MenuNavigator.HOLD_SAVE_MS : MenuNavigator.HOLD_APPLY_MS;
        double p = nav.holdProgress(nowMs, total);
        if (p > 0) {
            int filled = (int) Math.round(p * BAR);
            StringBuilder bar = new StringBuilder("hold [");
            for (int i = 0; i < BAR; i++) bar.append(i < filled ? '#' : '-');
            return bar.append("] ").append(saveHold ? "save as air default" : "apply").toString();
        }
        return nav.hint().isEmpty() ? CONTROLS : nav.hint();
    }

    static String pad(String s, int width) {
        if (s.length() >= width) return s.substring(0, width - 1) + " ";
        return String.format(Locale.US, "%-" + width + "s", s);
    }

    static String fit(String s) {
        return s.length() <= COLUMNS ? s : s.substring(0, COLUMNS);
    }

    private static String rtrim(String s) {
        int end = s.length();
        while (end > 0 && s.charAt(end - 1) == ' ') end--;
        return s.substring(0, end);
    }
}
