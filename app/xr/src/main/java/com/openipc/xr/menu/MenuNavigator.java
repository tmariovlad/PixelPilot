package com.openipc.xr.menu;

import com.openipc.xr.XrBridge;

import java.util.ArrayDeque;
import java.util.Deque;
import java.util.List;
import java.util.Locale;

/**
 * The menu's state machine for the right thumbstick alone (docs/xr/menu-design.md §3). Closed, only a 1 s click hold
 * opens it. Browsing: up/down move (wrapping), right or a click enters, toggles or starts an edit, left goes back.
 * Editing: left/right change the value, a click applies a Quest option, a 1 s hold applies an air option, up/down or
 * {@link #EDIT_IDLE_MS} cancel. A 3 s hold on an air line saves the air's default. The menu closes after
 * {@link #IDLE_CLOSE_MS} without input, except on a stats page. Pure logic with an injected clock; UI thread only.
 */
public final class MenuNavigator {
    public static final long HOLD_OPEN_MS = 1000;
    public static final long HOLD_APPLY_MS = 1000;
    public static final long HOLD_SAVE_MS = 3000;
    public static final long IDLE_CLOSE_MS = 20000;
    public static final long EDIT_IDLE_MS = 6000;
    /** The action line that closes the menu. */
    public static final String CLOSE_ID = "close";
    static final String HINT_HOLD_AIR = "hold 1 s to apply";

    private static final int STICK = XrBridge.INPUT_STICK_LEFT | XrBridge.INPUT_STICK_RIGHT | XrBridge.INPUT_STICK_UP
            | XrBridge.INPUT_STICK_DOWN;

    private static final class Level {
        final MenuItem folder;
        int index;

        Level(MenuItem folder) {
            this.folder = folder;
        }
    }

    private final MenuModel model;
    private final Deque<Level> stack = new ArrayDeque<>();
    private MenuItem pageItem;          // the stats page being shown, or null
    private boolean open;
    private boolean editing;
    private int editChoice;             // index into the choices while editing a choice or an air boolean
    private int editNumber;             // value while editing a number
    private String hint = "";
    private long pressMs = -1;          // thumbstick click held since, or -1
    private boolean fired;              // the current hold already did something
    private long lastInputMs;

    public MenuNavigator(MenuItem root, MenuModel model) {
        if (root.kind != MenuItem.Kind.FOLDER) throw new IllegalArgumentException("root must be a folder");
        this.model = model;
        stack.push(new Level(root));
    }

    public boolean isOpen() {
        return open;
    }

    public boolean isEditing() {
        return editing;
    }

    /** The folder or stats page on screen. */
    public MenuItem page() {
        return pageItem != null ? pageItem : stack.peek().folder;
    }

    /** From the root to the page on screen (a stats page included). */
    public List<MenuItem> path() {
        List<MenuItem> out = new java.util.ArrayList<>();
        java.util.Iterator<Level> it = stack.descendingIterator();
        while (it.hasNext()) out.add(it.next().folder);
        if (pageItem != null) out.add(pageItem);
        return out;
    }

    /** The highlighted line of the current folder (the page itself on a stats page). */
    public MenuItem highlighted() {
        if (pageItem != null) return pageItem;
        Level l = stack.peek();
        return l.folder.children.get(l.index);
    }

    /** The value being edited, or null when not editing. */
    public String pendingValue() {
        if (!editing) return null;
        MenuItem it = highlighted();
        return it.kind == MenuItem.Kind.NUMBER ? Integer.toString(editNumber) : choicesOf(it).get(editChoice);
    }

    /** A short instruction for the pilot, "" if none. */
    public String hint() {
        return hint;
    }

    /** How far the current click hold is towards {@code totalMs}, 0..1 (0 when the click is up or the hold already acted). */
    public double holdProgress(long nowMs, long totalMs) {
        if (pressMs < 0 || fired) return 0;
        return Math.min(1.0, (nowMs - pressMs) / (double) totalMs);
    }

    /** Applies the input bits of one tick. Returns what the pilot confirmed, or null. */
    public MenuAction update(int events, long nowMs) {
        if ((events & XrBridge.INPUT_STICK_PRESS) != 0) {
            pressMs = nowMs;
            fired = false;
            lastInputMs = nowMs;
        }
        boolean release = (events & XrBridge.INPUT_STICK_RELEASE) != 0;
        if (!open) {
            if (pressMs >= 0 && !fired && nowMs - pressMs >= HOLD_OPEN_MS) {
                open = true;
                fired = true;
                hint = "";
                lastInputMs = nowMs;
            }
            if (release) pressMs = -1;
            return null;
        }
        MenuAction action = null;
        if ((events & STICK) != 0) {
            lastInputMs = nowMs;
            action = onStick(events);
        }
        if (open && pressMs >= 0 && !fired && action == null) action = onHold(nowMs - pressMs);
        if (release) {
            if (open && pressMs >= 0 && !fired && nowMs - pressMs < HOLD_APPLY_MS && action == null) action = onClick();
            pressMs = -1;
            lastInputMs = nowMs;
        }
        if (editing && pressMs < 0 && nowMs - lastInputMs >= EDIT_IDLE_MS) stopEdit();
        if (open && pageItem == null && pressMs < 0 && nowMs - lastInputMs >= IDLE_CLOSE_MS) close();
        return action;
    }

    private MenuAction onStick(int events) {
        boolean left = (events & XrBridge.INPUT_STICK_LEFT) != 0;
        boolean right = (events & XrBridge.INPUT_STICK_RIGHT) != 0;
        boolean vertical = (events & (XrBridge.INPUT_STICK_UP | XrBridge.INPUT_STICK_DOWN)) != 0;
        if (editing) {
            if (vertical) {
                stopEdit();
            } else if (left || right) {
                stepEdit(right ? 1 : -1);
            }
            return null;
        }
        if (pageItem != null) {
            if (left) pageItem = null;
            return null;
        }
        Level l = stack.peek();
        int n = l.folder.children.size();
        if ((events & XrBridge.INPUT_STICK_UP) != 0) l.index = (l.index - 1 + n) % n;
        if ((events & XrBridge.INPUT_STICK_DOWN) != 0) l.index = (l.index + 1) % n;
        if (vertical) hint = "";
        if (right) return activate(highlighted());
        if (left) back();
        return null;
    }

    private MenuAction onClick() {
        if (pageItem != null) return null;
        if (!editing) return activate(highlighted());
        MenuItem it = highlighted();
        if (it.apply.isAir()) {
            hint = HINT_HOLD_AIR;
            return null;
        }
        return finishEdit(MenuAction.Type.SET);
    }

    private MenuAction onHold(long heldMs) {
        if (pageItem != null) return null;
        MenuItem it = highlighted();
        if (editing && heldMs >= HOLD_APPLY_MS) {
            fired = true;
            return finishEdit(it.apply.isAir() ? MenuAction.Type.APPLY_AIR : MenuAction.Type.SET);
        }
        if (!editing && heldMs >= HOLD_SAVE_MS && it.isOption() && it.apply.isAir() && model.available(it.id)) {
            fired = true;
            return new MenuAction(MenuAction.Type.SAVE_AIR_DEFAULT, it, model.value(it.id));
        }
        return null;
    }

    private MenuAction activate(MenuItem it) {
        if (!model.available(it.id)) return null;
        switch (it.kind) {
            case FOLDER:
                stack.push(new Level(it));
                return null;
            case PAGE:
                pageItem = it;
                return null;
            case ACTION:
                if (CLOSE_ID.equals(it.id)) {
                    close();
                    return null;
                }
                return new MenuAction(MenuAction.Type.RUN, it, null);
            case BOOL:
                if (!it.apply.isAir()) {
                    return new MenuAction(MenuAction.Type.SET, it, Boolean.toString(!"true".equals(model.value(it.id))));
                }
                // fall through: an air boolean is edited like a choice, so it needs the hold
            default:
                return startEdit(it);
        }
    }

    private MenuAction startEdit(MenuItem it) {
        if (it.kind == MenuItem.Kind.NUMBER) {
            editNumber = parseOr(model.value(it.id), it.min);
            editNumber = Math.max(it.min, Math.min(it.max, editNumber));
        } else {
            List<String> c = choicesOf(it);
            if (c == null || c.isEmpty()) return null;
            editChoice = Math.max(0, c.indexOf(model.value(it.id)));
        }
        editing = true;
        hint = it.apply.isAir() ? HINT_HOLD_AIR : "";
        return null;
    }

    private void stepEdit(int dir) {
        MenuItem it = highlighted();
        if (it.kind == MenuItem.Kind.NUMBER) {
            editNumber = Math.max(it.min, Math.min(it.max, editNumber + dir * it.step));
        } else {
            editChoice = Math.max(0, Math.min(choicesOf(it).size() - 1, editChoice + dir));
        }
    }

    private MenuAction finishEdit(MenuAction.Type type) {
        MenuAction a = new MenuAction(type, highlighted(), pendingValue());
        stopEdit();
        return a;
    }

    private void stopEdit() {
        editing = false;
        hint = "";
    }

    private void back() {
        if (stack.size() > 1) {
            stack.pop();
        } else {
            close();
        }
    }

    private void close() {
        open = false;
        editing = false;
        pageItem = null;
        fired = true;       // a hold that closed the menu must not fire again
        pressMs = -1;
        hint = "";
    }

    private List<String> choicesOf(MenuItem it) {
        if (it.kind == MenuItem.Kind.BOOL) return java.util.Arrays.asList("false", "true");
        return model.choices(it.id);
    }

    private static int parseOr(String s, int fallback) {
        try {
            return s == null ? fallback : Integer.parseInt(s.trim().toLowerCase(Locale.US));
        } catch (NumberFormatException e) {
            return fallback;
        }
    }
}
