package com.openipc.xr.menu;

import static org.junit.Assert.*;

import com.openipc.xr.OptionCosts;

import org.junit.Test;

/** The cost column of the menu, formatted from the one cost table (option_costs.json, OptionCosts). */
public class OptionCostLabelsTest {
    static final String JSON = "{\"schema\": 1, \"updated\": \"2026-09-29\", \"list_presets\": [\"race\"], \"options\": ["
            + "{\"id\": \"lever.fif\", \"group\": \"lever\", \"label\": \"FIF\", \"key\": \"feed_incomplete_frames\","
            + " \"costs\": {\"fps\": {\"off\": [82.4, 84.1], \"on\": [89.2, 89.6]}}, \"note\": \"smears on loss\","
            + " \"tag\": \"PROVEN\", \"source\": \"docs/xr/link-envelope.md\", \"measured\": \"2026-09-29\"},"
            + "{\"id\": \"bitrate.4000\", \"group\": \"bitrate\", \"label\": \"4 Mbit/s\", \"key\": \"4000\","
            + " \"costs\": {\"delta_ms\": {\"mean\": 1.7, \"vs\": \"bitrate.2000\"}}, \"tag\": \"INFERRED\","
            + " \"source\": \"docs/xr/g2g-budget.md\", \"measured\": \"2026-09-27\"},"
            + "{\"id\": \"lever.frz\", \"group\": \"lever\", \"label\": \"FRZ\", \"key\": \"freeze_until_idr\","
            + " \"costs\": {\"range_note\": \"hold ~0.1-0.3 s, not measured\"}, \"note\": \"brief hold on loss\", \"tag\": \"SPECULATION\","
            + " \"source\": \"docs/xr/link-envelope.md\", \"measured\": \"2026-09-29\"}"
            + "]}";

    static final MenuItem FIF = MenuItem.bool("feed_incomplete_frames", "Feed incomplete", ApplyClass.LIVE);
    static final MenuItem FRZ = MenuItem.bool("freeze_until_idr", "Freeze until IDR", ApplyClass.LIVE);
    static final MenuItem QUALITY = MenuItem.choice("air.quality", "Quality", ApplyClass.AIR);
    static final MenuItem OTHER = MenuItem.bool("xr_flip_vertical", "Flip", ApplyClass.LIVE);

    static OptionCostLabels labels(String qualityValue) {
        OptionCosts costs = OptionCosts.parse(JSON);
        return new OptionCostLabels(costs, item -> {
            if (item == QUALITY) return new String[]{"bitrate", qualityValue};
            if (item.apply == ApplyClass.LIVE || item.apply == ApplyClass.RELAUNCH) return new String[]{"lever", item.id};
            return null;
        });
    }

    @Test public void aLeverShowsFpsOffToOnAndItsNote() {
        assertEquals("fps 83>89, smears on loss", labels("2000").label(FIF));
    }

    @Test public void aMeasuredDeltaIsSigned() {
        assertEquals("+1.7 ms", labels("4000").label(QUALITY));
    }

    @Test public void aNoteAloneAndAnUnmeasuredEntryShowOnlyTheNoteOrNothing() {
        assertEquals("brief hold on loss (est.)", labels("2000").label(FRZ));
        assertEquals("", labels("2000").label(OTHER));
        assertEquals("", labels("6000").label(QUALITY));
    }
}
