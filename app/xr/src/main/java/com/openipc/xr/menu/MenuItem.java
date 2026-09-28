package com.openipc.xr.menu;

import java.util.Arrays;
import java.util.Collections;
import java.util.List;

/**
 * One line of the menu tree (docs/xr/menu-design.md §5): a folder, a stats page, an action, or an option with its
 * kind, apply class and, for numbers, range and step. Values and choices come from {@link MenuModel}. Immutable.
 */
public final class MenuItem {
    public enum Kind { FOLDER, PAGE, ACTION, BOOL, CHOICE, NUMBER }

    public final String id;
    public final String label;
    public final Kind kind;
    public final ApplyClass apply;
    public final List<MenuItem> children;
    public final int min, max, step;
    public final String unit;

    private MenuItem(String id, String label, Kind kind, ApplyClass apply, List<MenuItem> children, int min, int max,
            int step, String unit) {
        this.id = id;
        this.label = label;
        this.kind = kind;
        this.apply = apply;
        this.children = children;
        this.min = min;
        this.max = max;
        this.step = step;
        this.unit = unit;
    }

    public static MenuItem folder(String id, String label, MenuItem... children) {
        if (children.length == 0) throw new IllegalArgumentException("empty folder " + id);
        return new MenuItem(id, label, Kind.FOLDER, ApplyClass.NONE,
                Collections.unmodifiableList(Arrays.asList(children)), 0, 0, 0, "");
    }

    public static MenuItem page(String id, String label) {
        return new MenuItem(id, label, Kind.PAGE, ApplyClass.NONE, Collections.emptyList(), 0, 0, 0, "");
    }

    public static MenuItem action(String id, String label) {
        return new MenuItem(id, label, Kind.ACTION, ApplyClass.NONE, Collections.emptyList(), 0, 0, 0, "");
    }

    public static MenuItem bool(String id, String label, ApplyClass apply) {
        return new MenuItem(id, label, Kind.BOOL, apply, Collections.emptyList(), 0, 0, 0, "");
    }

    public static MenuItem choice(String id, String label, ApplyClass apply) {
        return new MenuItem(id, label, Kind.CHOICE, apply, Collections.emptyList(), 0, 0, 0, "");
    }

    public static MenuItem number(String id, String label, ApplyClass apply, int min, int max, int step, String unit) {
        if (step <= 0 || max < min) throw new IllegalArgumentException("bad range for " + id);
        return new MenuItem(id, label, Kind.NUMBER, apply, Collections.emptyList(), min, max, step, unit);
    }

    public boolean isOption() {
        return kind == Kind.BOOL || kind == Kind.CHOICE || kind == Kind.NUMBER;
    }

    /** The first item with this id in the subtree, or null. */
    public MenuItem find(String wanted) {
        if (id.equals(wanted)) return this;
        for (MenuItem c : children) {
            MenuItem f = c.find(wanted);
            if (f != null) return f;
        }
        return null;
    }
}
