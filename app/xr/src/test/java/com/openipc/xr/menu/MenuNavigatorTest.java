package com.openipc.xr.menu;

import static com.openipc.xr.XrBridge.INPUT_STICK_DOWN;
import static com.openipc.xr.XrBridge.INPUT_STICK_LEFT;
import static com.openipc.xr.XrBridge.INPUT_STICK_PRESS;
import static com.openipc.xr.XrBridge.INPUT_STICK_RELEASE;
import static com.openipc.xr.XrBridge.INPUT_STICK_RIGHT;
import static com.openipc.xr.XrBridge.INPUT_STICK_UP;
import static org.junit.Assert.*;

import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.junit.Before;
import org.junit.Test;

/** The right-stick controls of docs/xr/menu-design.md §3, row by row. */
public class MenuNavigatorTest {
    static final class FakeModel implements MenuModel {
        final Map<String, String> values = new HashMap<>();
        final Map<String, List<String>> choices = new HashMap<>();
        final Set<String> unavailable = new HashSet<>();
        @Override public String value(String id) { return values.get(id); }
        @Override public List<String> choices(String id) { return choices.get(id); }
        @Override public boolean available(String id) { return !unavailable.contains(id); }
    }

    static final MenuItem TREE = MenuItem.folder("root", "Menu",
            MenuItem.page("stats", "Stats"),
            MenuItem.folder("picture", "Picture",
                    MenuItem.bool("fif", "Feed incomplete", ApplyClass.LIVE),
                    MenuItem.number("idr_ms", "Keyframe interval", ApplyClass.LIVE, 100, 2000, 100, "ms"),
                    MenuItem.choice("refresh", "Refresh", ApplyClass.RELAUNCH)),
            MenuItem.folder("air", "Air",
                    MenuItem.choice("mode", "Mode", ApplyClass.AIR),
                    MenuItem.choice("codec", "Codec", ApplyClass.AIR)),
            MenuItem.action("close", "Close"));

    FakeModel model;
    MenuNavigator nav;
    long t;

    @Before public void setUp() {
        model = new FakeModel();
        model.values.put("fif", "false");
        model.values.put("idr_ms", "200");
        model.values.put("refresh", "90");
        model.choices.put("refresh", Arrays.asList("72", "90", "120"));
        model.values.put("mode", "race");
        model.choices.put("mode", Arrays.asList("race", "balanced", "wide"));
        model.values.put("codec", "h264");
        model.choices.put("codec", Arrays.asList("h264", "h265"));
        model.unavailable.add("codec");
        nav = new MenuNavigator(TREE, model);
        t = 1000;
    }

    MenuAction tick(int events) {
        t += 50;
        return nav.update(events, t);
    }

    MenuAction hold(long ms) {
        MenuAction a = tick(INPUT_STICK_PRESS);
        long end = t + ms;
        while (t < end) {
            MenuAction b = tick(0);
            if (b != null) a = b;
        }
        return a;
    }

    MenuAction click() {
        tick(INPUT_STICK_PRESS);
        return tick(INPUT_STICK_RELEASE);
    }

    void open() {
        hold(1000);
        tick(INPUT_STICK_RELEASE);
        assertTrue(nav.isOpen());
    }

    @Test public void closedMenuIgnoresFlicksAndShortClicks() {
        for (int e : new int[]{INPUT_STICK_LEFT, INPUT_STICK_RIGHT, INPUT_STICK_UP, INPUT_STICK_DOWN}) {
            assertNull(tick(e));
            assertFalse(nav.isOpen());
        }
        click();
        assertFalse(nav.isOpen());
    }

    @Test public void clickHeldOneSecondOpensAndItsReleaseDoesNothingElse() {
        hold(900);
        assertFalse(nav.isOpen());
        hold(1000);
        assertTrue(nav.isOpen());
        assertNull(tick(INPUT_STICK_RELEASE));
        assertEquals("stats", nav.highlighted().id);
        assertEquals("root", nav.page().id);
    }

    @Test public void upDownMoveAndWrap() {
        open();
        tick(INPUT_STICK_DOWN);
        assertEquals("picture", nav.highlighted().id);
        tick(INPUT_STICK_UP);
        tick(INPUT_STICK_UP);
        assertEquals("close", nav.highlighted().id);
    }

    @Test public void rightEntersAFolderAndLeftGoesBackThenCloses() {
        open();
        tick(INPUT_STICK_DOWN);
        tick(INPUT_STICK_RIGHT);
        assertEquals("picture", nav.page().id);
        assertEquals("fif", nav.highlighted().id);
        tick(INPUT_STICK_LEFT);
        assertEquals("root", nav.page().id);
        assertEquals("picture", nav.highlighted().id);
        tick(INPUT_STICK_LEFT);
        assertFalse(nav.isOpen());
    }

    @Test public void aShortClickEntersAFolderLikeRight() {
        open();
        tick(INPUT_STICK_DOWN);
        click();
        assertEquals("picture", nav.page().id);
    }

    @Test public void rightOnABooleanTogglesIt() {
        open();
        tick(INPUT_STICK_DOWN);
        tick(INPUT_STICK_RIGHT);
        MenuAction a = tick(INPUT_STICK_RIGHT);
        assertEquals(MenuAction.Type.SET, a.type);
        assertEquals("fif", a.item.id);
        assertEquals("true", a.value);
    }

    @Test public void editANumberStepsClampsAndAppliesOnClick() {
        open();
        tick(INPUT_STICK_DOWN);
        tick(INPUT_STICK_RIGHT);
        tick(INPUT_STICK_DOWN);                    // idr_ms
        assertNull(tick(INPUT_STICK_RIGHT));       // starts editing, nothing applied yet
        assertTrue(nav.isEditing());
        tick(INPUT_STICK_LEFT);                    // 100
        tick(INPUT_STICK_LEFT);                    // clamped at 100
        assertEquals("100", nav.pendingValue());
        MenuAction a = click();
        assertEquals(MenuAction.Type.SET, a.type);
        assertEquals("100", a.value);
        assertFalse(nav.isEditing());
    }

    @Test public void editAChoiceCancelsOnUpDownAndOnIdle() {
        open();
        tick(INPUT_STICK_DOWN);
        tick(INPUT_STICK_RIGHT);
        tick(INPUT_STICK_UP);                      // refresh (wraps from fif)
        assertEquals("refresh", nav.highlighted().id);
        tick(INPUT_STICK_RIGHT);
        tick(INPUT_STICK_RIGHT);
        assertEquals("120", nav.pendingValue());
        tick(INPUT_STICK_DOWN);
        assertFalse(nav.isEditing());
        tick(INPUT_STICK_RIGHT);
        tick(INPUT_STICK_LEFT);
        assertEquals("72", nav.pendingValue());
        t += MenuNavigator.EDIT_IDLE_MS;
        assertNull(tick(0));
        assertFalse(nav.isEditing());
        assertTrue(nav.isOpen());
    }

    @Test public void anAirOptionNeedsAOneSecondHoldAndAClickOnlyHints() {
        open();
        tick(INPUT_STICK_DOWN);
        tick(INPUT_STICK_DOWN);
        tick(INPUT_STICK_RIGHT);                   // air page, mode
        tick(INPUT_STICK_RIGHT);                   // edit
        tick(INPUT_STICK_RIGHT);                   // balanced
        assertNull(click());
        assertTrue(nav.isEditing());
        assertEquals("hold 1 s to apply", nav.hint());
        MenuAction a = hold(1000);
        assertEquals(MenuAction.Type.APPLY_AIR, a.type);
        assertEquals("mode", a.item.id);
        assertEquals("balanced", a.value);
        tick(INPUT_STICK_RELEASE);
        assertFalse(nav.isEditing());
    }

    @Test public void holdingThreeSecondsOnTheActiveAirValueSavesTheDefault() {
        open();
        tick(INPUT_STICK_DOWN);
        tick(INPUT_STICK_DOWN);
        tick(INPUT_STICK_RIGHT);                   // highlight on mode, not editing
        MenuAction a = hold(3000);
        assertEquals(MenuAction.Type.SAVE_AIR_DEFAULT, a.type);
        assertEquals("mode", a.item.id);
    }

    @Test public void anUnavailableLineDoesNothing() {
        open();
        tick(INPUT_STICK_DOWN);
        tick(INPUT_STICK_DOWN);
        tick(INPUT_STICK_RIGHT);
        tick(INPUT_STICK_DOWN);                    // codec, unavailable
        assertNull(tick(INPUT_STICK_RIGHT));
        assertFalse(nav.isEditing());
        assertNull(hold(3000));
    }

    @Test public void theCloseLineClosesAndIdleClosesButNotOnAStatsPage() {
        open();
        tick(INPUT_STICK_UP);                      // close
        click();
        assertFalse(nav.isOpen());
        open();                                    // reopens where it was
        assertEquals("close", nav.highlighted().id);
        t += MenuNavigator.IDLE_CLOSE_MS;
        tick(0);
        assertFalse(nav.isOpen());
        open();
        tick(INPUT_STICK_DOWN);                    // stats
        tick(INPUT_STICK_RIGHT);
        assertEquals("stats", nav.page().id);
        t += 10 * MenuNavigator.IDLE_CLOSE_MS;
        tick(0);
        assertTrue(nav.isOpen());
        tick(INPUT_STICK_LEFT);
        assertEquals("root", nav.page().id);
    }

    @Test public void holdProgressFillsWhileTheClickIsDown() {
        tick(INPUT_STICK_PRESS);
        t += 450;
        tick(0);
        assertEquals(0.5, nav.holdProgress(t, MenuNavigator.HOLD_OPEN_MS), 0.01);
        tick(INPUT_STICK_RELEASE);
        assertEquals(0.0, nav.holdProgress(t, MenuNavigator.HOLD_OPEN_MS), 0.0);
        hold(1000);                                // opens: the hold has acted, so no bar
        assertTrue(nav.isOpen());
        assertEquals(0.0, nav.holdProgress(t, MenuNavigator.HOLD_APPLY_MS), 0.0);
    }
}
