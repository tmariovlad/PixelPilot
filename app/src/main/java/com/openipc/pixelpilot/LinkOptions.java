package com.openipc.pixelpilot;

import android.content.Context;
import android.content.SharedPreferences;

import com.openipc.wfbngrtl8812.WfbNgLink;

/**
 * Applies the user's link options (adaptive link, TX power, FEC, LDPC, STBC, FEC thresholds) from the
 * "general" preferences to a {@link WfbNgLink}. Both the 2D and the XR activity own their own link, so both
 * call this; otherwise the XR link runs with the native defaults whatever the user chose in the menu.
 */
final class LinkOptions {
    private LinkOptions() {}

    static void apply(Context context, WfbNgLink link) {
        SharedPreferences prefs = context.getSharedPreferences("general", Context.MODE_PRIVATE);
        link.nativeSetAdaptiveLinkEnabled(prefs.getBoolean("adaptive_link_enabled", true));
        link.nativeSetTxPower(prefs.getInt("adaptive_tx_power", 20));
        link.nativeSetUseFec(prefs.getBoolean("custom_fec_enabled", true) ? 1 : 0);
        link.nativeSetUseLdpc(prefs.getBoolean("custom_ldpc_enabled", true) ? 1 : 0);
        link.nativeSetUseStbc(prefs.getBoolean("custom_stbc_enabled", true) ? 1 : 0);
        applyFecThresholds(context, link);
        Uplink up = Uplink.from(prefs::getInt);
        link.setUplink(up.rateHz, up.fecK, up.fecN, up.mcs);
    }

    static void applyFecThresholds(Context context, WfbNgLink link) {
        SharedPreferences prefs = context.getSharedPreferences("general", Context.MODE_PRIVATE);
        link.setFecThresholds(
                prefs.getInt("fec_lost_to_5", 2),
                prefs.getInt("fec_recovered_to_4", 30),
                prefs.getInt("fec_recovered_to_3", 24),
                prefs.getInt("fec_recovered_to_2", 14),
                prefs.getInt("fec_recovered_to_1", 8));
    }

    /**
     * Airtime of the uplink (adaptive-link reports + tunnel uplink, radio port 160). Upstream sends 10 reports/s with
     * FEC 1/5 at MCS0, ~51 frames/s, which took measurable airtime from the video (docs/xr/link-envelope.md). The
     * defaults here are the app's: 4 reports/s x FEC 1/3 = 12 frames/s. News (a new IDR request, a changed
     * fec_change) still goes out at once (UplinkSchedule.h), so the lower rate does not delay keyframe requests.
     * The air unit's alink falls back when no report arrives for its timeout, which must stay well above 1/rate.
     */
    static final class Uplink {
        static final String RATE_HZ = "uplink_rate_hz";
        static final String FEC_K = "uplink_fec_k";
        static final String FEC_N = "uplink_fec_n";
        static final String MCS = "uplink_mcs";

        interface Ints {
            int get(String key, int defaultValue);
        }

        final int rateHz, fecK, fecN, mcs;

        private Uplink(int rateHz, int fecK, int fecN, int mcs) {
            this.rateHz = rateHz;
            this.fecK = fecK;
            this.fecN = fecN;
            this.mcs = mcs;
        }

        static Uplink from(Ints prefs) {
            return new Uplink(prefs.get(RATE_HZ, 4), prefs.get(FEC_K, 1), prefs.get(FEC_N, 3), prefs.get(MCS, 0));
        }

        /** Frames on air per second when there is no news and no tunnel traffic. */
        int framesPerSecond() {
            return rateHz * fecN / fecK;
        }
    }
}
