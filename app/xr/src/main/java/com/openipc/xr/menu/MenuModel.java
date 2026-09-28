package com.openipc.xr.menu;

import java.util.List;

/**
 * What the menu shows for each option, supplied by the app: current values from the prefs and from the air's state,
 * choices from the air's {@code list} or the app's own tables. The menu tree holds no data (docs/xr/menu-design.md).
 */
public interface MenuModel {
    /** The current value as text ("true"/"false" for a boolean, a number, a choice); null if unknown. */
    String value(String id);

    /** The allowed values of a choice, in order; null or empty if none are known yet. */
    List<String> choices(String id);

    /** False greys the line out and ignores input on it (e.g. an air option the air does not list yet). */
    boolean available(String id);
}
