package com.openipc.xr.menu;

import static com.openipc.xr.XrBridge.INPUT_STICK_DOWN;
import static com.openipc.xr.XrBridge.INPUT_STICK_PRESS;
import static com.openipc.xr.XrBridge.INPUT_STICK_RIGHT;
import static org.junit.Assert.*;

import java.util.Arrays;
import java.util.Collections;
import java.util.List;

import org.junit.Before;
import org.junit.Test;

/** Menu pages as lines (docs/xr/menu-design.md §5): label, value, apply tag, cost; highlight, edit, greyed-out lines. */
public class MenuRendererTest {
    MenuNavigatorTest.FakeModel model;
    MenuNavigator nav;
    MenuRenderer renderer;
    long t = 1000;

    @Before public void setUp() {
        MenuNavigatorTest t0 = new MenuNavigatorTest();
        t0.setUp();
        model = t0.model;
        nav = new MenuNavigator(MenuNavigatorTest.TREE, model);
        MenuRenderer.CostLabels costs = item -> item.id.equals("fif") ? "+fps, smears on loss" : "";
        PageSource pages = id -> id.equals("stats") ? Arrays.asList("G2G est. 31.4 ms", "fps 89.6") : Collections.emptyList();
        renderer = new MenuRenderer(model, costs, pages);
        nav.update(INPUT_STICK_PRESS, t);
        nav.update(0, t += 1000);          // open
        nav.update(com.openipc.xr.XrBridge.INPUT_STICK_RELEASE, t += 50);
    }

    List<MenuLine> render() {
        return renderer.render(nav, t);
    }

    @Test public void theRootPageListsItsLinesUnderATitleWithTheHighlightMarked() {
        List<MenuLine> l = render();
        assertEquals(MenuLine.Style.TITLE, l.get(0).style);
        assertEquals("MENU", l.get(0).text.trim());
        assertEquals(MenuLine.Style.HIGHLIGHT, l.get(1).style);
        assertTrue(l.get(1).text, l.get(1).text.startsWith("> Stats"));
        assertTrue(l.get(2).text, l.get(2).text.startsWith("  Picture"));
        assertEquals(MenuLine.Style.NORMAL, l.get(2).style);
    }

    @Test public void anOptionLineShowsValueTagAndCostWithinTheWidth() {
        nav.update(INPUT_STICK_DOWN, t += 50);
        nav.update(INPUT_STICK_RIGHT, t += 50);           // Picture
        List<MenuLine> l = render();
        assertEquals("MENU > Picture", l.get(0).text.trim());
        String fif = l.get(1).text;
        assertTrue(fif, fif.startsWith("> Feed incomplete"));
        assertTrue(fif, fif.contains("OFF"));
        assertTrue(fif, fif.contains(" L "));
        assertTrue(fif, fif.endsWith("+fps, smears on loss"));
        assertTrue(l.get(2).text, l.get(2).text.contains("200 ms"));
        assertTrue(l.get(3).text, l.get(3).text.contains(" R"));
        for (MenuLine m : l) assertTrue(m.text, m.text.length() <= MenuRenderer.COLUMNS);
    }

    @Test public void anEditedValueIsBracketedAndTheAirHintShows() {
        nav.update(INPUT_STICK_DOWN, t += 50);
        nav.update(INPUT_STICK_DOWN, t += 50);
        nav.update(INPUT_STICK_RIGHT, t += 50);           // Air, mode
        nav.update(INPUT_STICK_RIGHT, t += 50);           // edit
        nav.update(INPUT_STICK_RIGHT, t += 50);           // balanced
        List<MenuLine> l = render();
        assertTrue(l.get(1).text, l.get(1).text.contains("<balanced>"));
        MenuLine last = l.get(l.size() - 1);
        assertEquals(MenuLine.Style.HINT, last.style);
        assertTrue(last.text, last.text.contains("hold 1 s to apply"));
    }

    @Test public void anUnavailableAirLineIsGreyedOutWithNeedsAir() {
        nav.update(INPUT_STICK_DOWN, t += 50);
        nav.update(INPUT_STICK_DOWN, t += 50);
        nav.update(INPUT_STICK_RIGHT, t += 50);
        MenuLine codec = render().get(2);
        assertEquals(MenuLine.Style.DISABLED, codec.style);
        assertTrue(codec.text, codec.text.contains("needs air"));
    }

    @Test public void aHeldClickShowsAFillingBar() {
        nav.update(INPUT_STICK_PRESS, t += 50);
        t += 500;
        MenuLine last = render().get(render().size() - 1);
        assertTrue(last.text, last.text.startsWith("hold ["));
        assertTrue(last.text, last.text.contains("#"));
    }

    @Test public void aStatsPageShowsItsSourceLines() {
        nav.update(INPUT_STICK_RIGHT, t += 50);           // Stats
        List<MenuLine> l = render();
        assertEquals("MENU > Stats", l.get(0).text.trim());
        assertEquals("G2G est. 31.4 ms", l.get(1).text);
        assertEquals("fps 89.6", l.get(2).text);
        assertTrue(l.get(l.size() - 1).text.contains("left: back"));
    }
}
