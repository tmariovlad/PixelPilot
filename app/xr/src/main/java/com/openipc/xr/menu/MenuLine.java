package com.openipc.xr.menu;

/** One text line of the menu layer and how to draw it. */
public final class MenuLine {
    public enum Style { TITLE, NORMAL, HIGHLIGHT, DISABLED, HINT }

    public final String text;
    public final Style style;

    public MenuLine(String text, Style style) {
        this.text = text;
        this.style = style;
    }

    @Override
    public String toString() {
        return style + " " + text;
    }
}
