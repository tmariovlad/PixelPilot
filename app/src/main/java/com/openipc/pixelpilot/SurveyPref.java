package com.openipc.pixelpilot;

import java.util.Map;

/**
 * The pre-flight channel survey switch (docs/xr/channel-survey-design.md, phase 1): off by default. When on, the next
 * link start sweeps the 5 GHz candidates for ~30 s before any video, logs PPXR_SURVEY, and then starts normally; the
 * native side runs it once per app launch, so a link restart in flight never repeats it.
 */
final class SurveyPref {
    static final String KEY = "survey_on_start";

    private SurveyPref() {
    }

    static boolean enabled(Map<String, ?> prefs) {
        return Boolean.TRUE.equals(prefs.get(KEY));
    }
}
