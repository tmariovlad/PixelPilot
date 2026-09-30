package com.openipc.pixelpilot;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import java.util.HashMap;
import java.util.Map;

import org.junit.Test;

/** The pre-flight channel survey is opt-in (docs/xr/channel-survey-design.md, phase 1). */
public class SurveyPrefTest {
    @Test
    public void offUnlessTheUserTurnsItOn() {
        Map<String, Object> prefs = new HashMap<>();
        assertFalse(SurveyPref.enabled(prefs));
        prefs.put(SurveyPref.KEY, true);
        assertTrue(SurveyPref.enabled(prefs));
        prefs.put(SurveyPref.KEY, "true");   // a malformed value is not a yes
        assertFalse(SurveyPref.enabled(prefs));
    }
}
