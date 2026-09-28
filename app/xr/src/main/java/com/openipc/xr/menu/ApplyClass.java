package com.openipc.xr.menu;

/** How a menu option takes effect (docs/xr/menu-design.md §4); {@link #tag} is shown on every line. */
public enum ApplyClass {
    /** Quest only, at once. */
    LIVE("L"),
    /** Quest only, through a controlled relaunch of the XR activity. */
    RELAUNCH("R"),
    /** The air unit, with a 1 s hold and confirm-or-rollback. */
    AIR("A"),
    /** The air unit and the Quest in step (channel). */
    AIR_AND_QUEST("A+Q"),
    /** Folders, pages and actions. */
    NONE("");

    public final String tag;

    ApplyClass(String tag) {
        this.tag = tag;
    }

    public boolean isAir() {
        return this == AIR || this == AIR_AND_QUEST;
    }
}
