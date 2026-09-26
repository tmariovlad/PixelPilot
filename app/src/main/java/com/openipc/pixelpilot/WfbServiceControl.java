package com.openipc.pixelpilot;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.net.VpnService;

/** Starts/stops the wfb-ng VPN service the same way from every activity. */
public final class WfbServiceControl {
    public static final int VPN_REQUEST_CODE = 100;

    private WfbServiceControl() {}

    /**
     * Starts the service if VPN permission is granted. Otherwise, when askIfMissing, asks for it
     * (the activity gets onActivityResult with VPN_REQUEST_CODE). Returns true if it started now.
     */
    public static boolean startVpn(Activity activity, boolean askIfMissing) {
        Intent consent = VpnService.prepare(activity);
        if (consent != null) {
            if (askIfMissing) activity.startActivityForResult(consent, VPN_REQUEST_CODE);
            return false;
        }
        activity.startService(new Intent(activity, WfbNgVpnService.class));
        return true;
    }

    public static void stopVpn(Context context) {
        Intent intent = new Intent(context, WfbNgVpnService.class);
        intent.setAction("STOP_SERVICE");
        context.startService(intent);
    }
}
