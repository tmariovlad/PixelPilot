package com.openipc.xr.menu;

/** What the pilot confirmed in the menu; the app carries it out according to the item's {@link ApplyClass}. */
public final class MenuAction {
    public enum Type {
        /** A Quest option gets a new value (live or relaunch, per the item's apply class). */
        SET,
        /** An air option gets a new value, confirmed by a 1 s hold. */
        APPLY_AIR,
        /** Save the air's active value as its boot default (3 s hold). */
        SAVE_AIR_DEFAULT,
        /** An action line was chosen (e.g. reset). */
        RUN
    }

    public final Type type;
    public final MenuItem item;
    public final String value;

    public MenuAction(Type type, MenuItem item, String value) {
        this.type = type;
        this.item = item;
        this.value = value;
    }

    @Override
    public String toString() {
        return type + " " + item.id + (value == null ? "" : "=" + value);
    }
}
