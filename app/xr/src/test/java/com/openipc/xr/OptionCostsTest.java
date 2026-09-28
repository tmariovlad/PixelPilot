package com.openipc.xr;

import static org.junit.Assert.*;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;

import org.junit.Test;

public class OptionCostsTest {
    /** The shipped table; Gradle runs unit tests from the module directory. */
    static String shipped() throws IOException {
        return new String(Files.readAllBytes(Paths.get("src/main/res/raw/option_costs.json")), StandardCharsets.UTF_8);
    }

    private static String table(String options) {
        return "{\"schema\":1,\"updated\":\"2026-09-29\",\"list_presets\":[\"race\",\"wide\"],\"options\":[" + options + "]}";
    }

    private static final String GOOD = "{\"id\":\"lever.fif\",\"group\":\"lever\",\"label\":\"FIF\","
            + "\"key\":\"feed_incomplete_frames\",\"costs\":{\"fps\":{\"off\":[82.4,84.1],\"on\":[89.2,89.6]}},"
            + "\"note\":\"smears on loss\",\"tag\":\"PROVEN\",\"source\":\"docs/xr/link-envelope.md#frame-fate\","
            + "\"measured\":\"2026-09-29\"}";

    private static void rejects(String options, String why) {
        try {
            OptionCosts.parse(table(options));
            fail("should reject: " + why);
        } catch (IllegalArgumentException expected) {
            assertTrue(expected.getMessage(), expected.getMessage().contains(why));
        }
    }

    @Test public void theShippedTableIsValid() throws IOException {
        OptionCosts c = OptionCosts.parse(shipped());
        assertFalse(c.options().isEmpty());
        for (OptionCosts.Option o : c.options()) {
            assertFalse(o.id, o.source.isEmpty());
            assertTrue(o.id, OptionCosts.TAGS.contains(o.tag));
        }
    }

    @Test public void theShippedTableCopiesNoNumberThatTheAirListOwns() throws IOException {
        OptionCosts c = OptionCosts.parse(shipped());
        for (String preset : c.listPresets()) {
            OptionCosts.Option o = c.byId("mode." + preset);
            if (o != null) assertFalse("mode." + preset + " copies g2g/fov from the air's list", o.hasListOwnedCost());
        }
    }

    @Test public void aGoodEntryParsesWithItsFields() {
        OptionCosts c = OptionCosts.parse(table(GOOD));
        OptionCosts.Option o = c.byKey("lever", "feed_incomplete_frames");
        assertEquals("lever.fif", o.id);
        assertEquals(82.4, o.fpsOff.lo, 0);
        assertEquals(84.1, o.fpsOff.hi, 0);
        assertEquals(89.2, o.fpsOn.lo, 0);
        assertFalse(o.fps.known());
        assertEquals("smears on loss", o.note);
    }

    @Test public void everyEntryNeedsASourceAndAKnownTag() {
        rejects(GOOD.replace("\"source\":\"docs/xr/link-envelope.md#frame-fate\"", "\"source\":\"\""), "source");
        rejects(GOOD.replace("\"PROVEN\"", "\"MEASURED\""), "tag");
    }

    @Test public void idsAreUniqueAndCarryTheirGroup() {
        rejects(GOOD + "," + GOOD, "duplicate id");
        rejects(GOOD.replace("\"lever.fif\"", "\"mode.fif\""), "group");
        rejects(GOOD.replace("\"group\":\"lever\"", "\"group\":\"colour\"").replace("lever.fif", "colour.fif"), "group");
    }

    @Test public void anUnknownCostFieldIsATypoNotSilence() {
        rejects(GOOD.replace("\"fps\"", "\"fsp\""), "unknown cost");
    }

    @Test public void anEntryWithoutAnyMeasuredValueIsRejected() {
        rejects(GOOD.replace("{\"fps\":{\"off\":[82.4,84.1],\"on\":[89.2,89.6]}}", "{}").replace(",\"note\":\"smears on loss\"", ""),
                "no measured value");
    }

    @Test public void theNoteIsShort() {
        rejects(GOOD.replace("smears on loss", "smears badly on every packet loss"), "note");
    }

    @Test public void aListPresetMustNotCarryG2gOrFov() {
        String wide = "{\"id\":\"mode.wide\",\"group\":\"mode\",\"label\":\"Wide\",\"key\":\"wide\","
                + "\"costs\":{\"g2g_ms\":[35.3,41.6]},\"tag\":\"PROVEN\",\"source\":\"x\",\"measured\":\"2026-09-27\"}";
        rejects(wide, "air's list");
    }

    @Test public void aModeTheAirDoesNotListYetMayCarryG2g() {
        String hd = "{\"id\":\"mode.hd\",\"group\":\"mode\",\"label\":\"HD\",\"key\":\"hd\","
                + "\"costs\":{\"g2g_ms\":[46.6,51.9],\"fps\":90.5},\"tag\":\"PROVEN\",\"source\":\"x\","
                + "\"measured\":\"2026-09-29\"}";
        OptionCosts.Option o = OptionCosts.parse(table(hd)).byId("mode.hd");
        assertEquals(46.6, o.g2g.lo, 0);
        assertEquals(51.9, o.g2g.hi, 0);
        assertEquals(90.5, o.fps.lo, 0);
        assertEquals(o.fps.lo, o.fps.hi, 0);
    }

    @Test public void aRangeMustBeTwoOrderedNumbers() {
        rejects(GOOD.replace("[82.4,84.1]", "[84.1,82.4]"), "range");
        rejects(GOOD.replace("[82.4,84.1]", "[82.4]"), "range");
    }

    @Test public void theDateIsIso() {
        rejects(GOOD.replace("2026-09-29", "29.09.2026"), "measured");
    }
}
