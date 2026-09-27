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
}
