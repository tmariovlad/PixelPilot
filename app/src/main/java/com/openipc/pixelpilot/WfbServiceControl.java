package com.openipc.pixelpilot;

import android.app.Activity;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.ServiceConnection;
import android.net.VpnService;
import android.os.IBinder;

/**
 * Runs the wfb-ng VPN tunnel the same way from every activity: by <em>binding</em> to {@link WfbNgVpnService}.
 *
 * <p>Not {@code startService()}: Android 8+ refuses it while the app's uid is idle
 * ({@code ActiveServices.startServiceLocked} -> {@code getAppStartModeLOSP}), which is the case when an activity is
 * created or resumed with the display off, e.g. the RTL adapter plugged in while the headset sleeps. The call then
 * throws {@code BackgroundServiceStartNotAllowedException} and kills the app. Binding has no such check, and the
 * service keeps the tunnel up exactly while at least one activity is bound.
 */
public final class WfbServiceControl {
    public static final int VPN_REQUEST_CODE = 100;
    /** The intent action {@link WfbNgVpnService#onBind} answers with the tunnel. */
    public static final String ACTION_BIND_TUNNEL = "com.openipc.pixelpilot.action.BIND_TUNNEL";

    private WfbServiceControl() {}

    /** One per activity: {@link #bind} in onResume, {@link #unbind} in onPause. */
    public static final class Binding {
        private final ServiceConnection connection = new ServiceConnection() {
            // The binding itself keeps the tunnel up; no binder calls are needed, so both callbacks are no-ops.
            @Override public void onServiceConnected(ComponentName name, IBinder service) { /* nothing to call */ }
            @Override public void onServiceDisconnected(ComponentName name) { /* the service restarts with the binding */ }
        };
        private boolean bound;

        /**
         * Binds to the tunnel if VPN permission is granted. Otherwise, when askIfMissing, asks for it (the activity
         * gets onActivityResult with VPN_REQUEST_CODE and should call bind again). Returns true if bound.
         */
        public boolean bind(Activity activity, boolean askIfMissing) {
            if (bound) return true;
            Intent consent = VpnService.prepare(activity);
            if (consent != null) {
                if (askIfMissing) activity.startActivityForResult(consent, VPN_REQUEST_CODE);
                return false;
            }
            bound = activity.bindService(tunnelIntent(activity), connection, Context.BIND_AUTO_CREATE);
            return bound;
        }

        public void unbind(Context context) {
            if (!bound) return;
            context.unbindService(connection);
            bound = false;
        }
    }

    static Intent tunnelIntent(Context context) {
        return new Intent(context, WfbNgVpnService.class).setAction(ACTION_BIND_TUNNEL);
    }
}
