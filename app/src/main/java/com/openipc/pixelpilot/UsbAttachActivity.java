package com.openipc.pixelpilot;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;

/**
 * Receives USB_DEVICE_ATTACHED for the RTL adapter instead of the 2D VideoActivity (audit X15, confirmed on the Quest
 * 2026-09-28: a replug in XR started the 2D activity, which left the pilot in 2D from the second replug on and started
 * a second link on the adapter XR already used). No display: it decides and finishes in onCreate.
 * <ul>
 *   <li>XR viewer started: nothing to do. Its WfbLinkManager receiver restarts the link on the attach (c27f8aa).</li>
 *   <li>Otherwise: the old behaviour, VideoActivity with the same intent (on a fresh start it autostarts XR).</li>
 * </ul>
 * Holding the filter here keeps the automatic USB permission that comes with an activity that declares the device.
 */
public final class UsbAttachActivity extends Activity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        if (!XrPresence.started()) {
            startActivity(new Intent(getIntent()).setClass(this, VideoActivity.class)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        }
        finish();
    }
}
