package com.openipc.pixelpilot;

import android.annotation.SuppressLint;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.hardware.usb.UsbDevice;
import android.hardware.usb.UsbManager;
import android.os.Build;
import android.util.Log;

import com.openipc.wfbngrtl8812.WfbNgLink;

import java.util.HashMap;
import java.util.Iterator;
import java.util.List;
import java.util.Map;

public class WfbLinkManager extends BroadcastReceiver {
    public static final String ACTION_USB_PERMISSION = "com.openipc.pixelpilot.USB_PERMISSION";
    private static final String TAG = "pixelpilot";
    static Map<String, UsbDevice> activeWifiAdapters = new HashMap<>();
    // Shared by the 2D and XR activities, like activeWifiAdapters: one permission request per attachment.
    static final UsbPermissionGate permissionGate = new UsbPermissionGate();
    // Restart decisions for links whose RX thread ended on its own, per adapter device name. UI thread.
    private final Map<String, RestartPolicy> restartPolicies = new HashMap<>();
    private final WfbNgLink wfbLink;
    private final LinkStatusListener status;
    private final Context context;
    private int wifiChannel;
    private Bandwidth bandWidth;

    public enum Bandwidth {
        BANDWIDTH_20(20),
        BANDWIDTH_40(40);

        private final int value;

        Bandwidth(int value) {
            this.value = value;
        }

        public int getValue() {
            return value;
        }

        /** 20 or 40 MHz; anything else (an old or hand-edited pref) falls back to 20 instead of leaving null. */
        public static Bandwidth fromMhz(int mhz) {
            return mhz == 40 ? BANDWIDTH_40 : BANDWIDTH_20;
        }
    }

    public WfbLinkManager(Context context, LinkStatusListener status, WfbNgLink wfbNgLink) {
        this.status = status;
        this.context = context;
        this.wfbLink = wfbNgLink;
    }

    /** Registers this receiver for its USB broadcasts, app-private where the platform allows it. */
    @SuppressLint("UnspecifiedRegisterReceiverFlag") // the flag only exists from API 33
    public void register() {
        if (Build.VERSION.SDK_INT >= 33) {
            context.registerReceiver(this, usbIntentFilter(), Context.RECEIVER_NOT_EXPORTED);
        } else {
            context.registerReceiver(this, usbIntentFilter());
        }
    }

    public void unregister() {
        try {
            context.unregisterReceiver(this);
        } catch (IllegalArgumentException ignored) {
            // was not registered
        }
    }

    /** The broadcasts this receiver handles. */
    private static IntentFilter usbIntentFilter() {
        IntentFilter filter = new IntentFilter();
        filter.addAction(UsbManager.ACTION_USB_DEVICE_ATTACHED);
        filter.addAction(UsbManager.ACTION_USB_DEVICE_DETACHED);
        filter.addAction(ACTION_USB_PERMISSION);
        return filter;
    }

    public void refreshKey() {
        wfbLink.refreshKey();
    }

    public void setChannel(int channel) {
        wifiChannel = channel;
    }
    public void setBandwidth(int bw) {
        // An unknown value used to leave bandWidth null, and startAdapter() then threw an NPE (audit X27).
        if (bw != 20 && bw != 40) Log.w(TAG, "unsupported bandwidth " + bw + " MHz, using 20");
        bandWidth = Bandwidth.fromMhz(bw);
    }

    @Override
    public synchronized void onReceive(Context context, Intent intent) {
        UsbDevice dev = intent.getParcelableExtra(UsbManager.EXTRA_DEVICE);
        if (android.hardware.usb.UsbManager.ACTION_USB_DEVICE_DETACHED.equals(intent.getAction())) {
            if (dev == null) {
                return;
            }
            Log.d(TAG, "usb device detached: " + dev.getVendorId() + "/" + dev.getProductId());
            refreshAdapters();
        } else if (android.hardware.usb.UsbManager.ACTION_USB_DEVICE_ATTACHED.equals(intent.getAction())) {
            if (dev == null) {
                return;
            }
            Log.d(TAG, "usb device attached: " + dev.getVendorId() + "/" + dev.getProductId());
            // The manifest may also route this to VideoActivity; refreshing here lets whichever activity is in
            // front (XR included) pick the adapter up. refreshAdapters() is idempotent for known adapters.
            refreshAdapters();
        } else if (ACTION_USB_PERMISSION.equals(intent.getAction())) {
            boolean granted = intent.getBooleanExtra(UsbManager.EXTRA_PERMISSION_GRANTED, false);
            Log.d(TAG, "usb permission " + (granted ? "granted" : "denied")
                    + (dev != null ? " for " + dev.getDeviceName() : ""));
            if (granted) refreshAdapters();
        }
    }

    public Map<String, UsbDevice> getAttachedAdapters() {
        android.hardware.usb.UsbManager manager =
                (android.hardware.usb.UsbManager) context.getSystemService(Context.USB_SERVICE);

        List<UsbDeviceFilter> filters;
        try {
            filters = UsbDeviceFilter.parseXml(context, R.xml.usb_device_filter);
        } catch (Exception e) {
            Log.e(TAG, "Unable to parse USB device filter", e);
            return new HashMap<>();
        }

        Map<String, UsbDevice> res = new HashMap<>();
        Map<String, UsbDevice> attached = manager.getDeviceList();
        // "No compatible wifi adapter found." is a common report, and the one thing needed to
        // act on it - the adapter's vendor and product id - was not obtainable. sysfs is not
        // readable by the shell on some devices (Horizon OS for one) and dumpsys usb does not
        // list host devices there either, so the app is the only thing that can report it.
        Log.i(TAG, "usb devices attached: " + attached.size());
        for (UsbDevice dev : attached.values()) {
            boolean allowed = false;
            for (UsbDeviceFilter filter : filters) {
                if (filter.productId == dev.getProductId() && filter.vendorId == dev.getVendorId()) {
                    allowed = true;
                    break;
                }
            }
            Log.i(TAG, String.format("  %s  %04X:%04X  %s %s  -> %s",
                    dev.getDeviceName(),
                    dev.getVendorId(),
                    dev.getProductId(),
                    String.valueOf(dev.getManufacturerName()),
                    String.valueOf(dev.getProductName()),
                    allowed ? "supported" : "NOT in usb_device_filter.xml"));
            if (!allowed) {
                continue;
            }
            res.put(dev.getDeviceName(), dev);
        }
        return res;
    }

    public synchronized void refreshAdapters() {
        Map<String, UsbDevice> attachedAdapters = getAttachedAdapters();
        if (attachedAdapters == null) {
            Log.e(TAG, "Could not read the usb device filter, skipping adapter refresh.");
            return;
        }

        boolean missingPermissions = false;
        android.hardware.usb.UsbManager usbManager =
                (android.hardware.usb.UsbManager) context.getSystemService(Context.USB_SERVICE);
        permissionGate.retainAttached(attachedAdapters.keySet());
        for (Map.Entry<String, UsbDevice> entry : attachedAdapters.entrySet()) {
            if (!usbManager.hasPermission(entry.getValue())) {
                if (!permissionGate.shouldAsk(entry.getKey())) {
                    // Asked once since it was plugged in: a denial must not turn every resume into a new prompt.
                    status.onLinkStatus("USB permission missing for " + entry.getValue().getDeviceName()
                            + " - replug the adapter to be asked again");
                    missingPermissions = true;
                    continue;
                }
                status.onLinkStatus("No permission for wifi adapter(s) " + entry.getValue().getDeviceName());
                // Android 14 refuses to deliver a PendingIntent built from an implicit
                // intent to a runtime registered receiver, so the permission result never
                // arrives unless the package is set explicitly.
                Intent permissionIntent = new Intent(WfbLinkManager.ACTION_USB_PERMISSION);
                permissionIntent.setPackage(context.getPackageName());
                PendingIntent pendingIntent = PendingIntent.getBroadcast(context, 0,
                        permissionIntent, PendingIntent.FLAG_IMMUTABLE);
                usbManager.requestPermission(entry.getValue(), pendingIntent);
                missingPermissions = true;
            }
        }

        if (missingPermissions) {
            return;
        }

        // Stops newly detached adapters.
        Iterator<Map.Entry<String, UsbDevice>> iterator = activeWifiAdapters.entrySet().iterator();
        while (iterator.hasNext()) {
            Map.Entry<String, UsbDevice> entry = iterator.next();
            if (attachedAdapters.containsKey(entry.getKey())) {
                continue;
            }
            stopAdapter(entry.getValue());
            iterator.remove();
        }

        // Starts newly attached adapters.
        boolean startFailed = false;
        for (Map.Entry<String, UsbDevice> entry : attachedAdapters.entrySet()) {
            if (activeWifiAdapters.containsKey(entry.getKey())) {
                continue;
            }
            // Only track it as active if it actually came up, otherwise a failed adapter
            // is never retried on the next refresh.
            if (startAdapter(entry.getValue())) {
                activeWifiAdapters.put(entry.getKey(), entry.getValue());
            } else {
                startFailed = true;
            }
        }

        if (activeWifiAdapters.isEmpty()) {
            // Now that a failed start no longer counts as active, an empty map covers two
            // different problems, and blaming the filter for both sends people looking in
            // the wrong place.
            String text = startFailed
                    ? "Wifi adapter found but could not be started - see the log."
                    : "No compatible wifi adapter found.";
            status.onLinkStatus(text);

            String wifi = VideoActivity.wirelessInfo(context);
            if (wifi != null) {
                status.onUdpFallbackAddress("udp://" + wifi + ":5600");
            }
        }
    }

    public synchronized void stopAdapters() {
        try {
            wfbLink.stopAll();
        } catch (InterruptedException ignored) {
        }
    }

    public synchronized void stopAdapter(UsbDevice dev) {
        try {
            wfbLink.stop(dev);
        } catch (InterruptedException e) {
            e.printStackTrace();
        }
    }

    /**
     * Restarts adapters whose RX thread ended on its own (lock timeout, CreateRtlDevice failure, a devourer error),
     * with {@link RestartPolicy}'s backoff. Call periodically while the activity is resumed (the XR stats tick).
     */
    public synchronized void checkHealth(long nowMs) {
        for (Map.Entry<String, UsbDevice> entry : activeWifiAdapters.entrySet()) {
            RestartPolicy policy = restartPolicies.get(entry.getKey());
            if (policy == null) {
                policy = new RestartPolicy();
                restartPolicies.put(entry.getKey(), policy);
            }
            if (policy.onTick(nowMs, wfbLink.isAlive(entry.getValue()))) {
                Log.w(TAG, "wfb-ng link on " + entry.getKey() + " ended; restart " + policy.attempts());
                status.onLinkStatus("link lost - restarting (" + policy.attempts() + ")");
                startAdapter(entry.getValue());
            }
        }
        restartPolicies.keySet().retainAll(activeWifiAdapters.keySet());
    }

    public synchronized void startAdapters() {
        if (wfbLink.isRunning()) {
            return;
        }
        for (Map.Entry<String, UsbDevice> entry : activeWifiAdapters.entrySet()) {
            if (!startAdapter(entry.getValue())) {
                break;
            }
        }
    }

    public synchronized boolean startAdapter(UsbDevice dev) {
        String text = "Starting wfb-ng channel " + wifiChannel + " with " + String.format(
                "[%04X", dev.getVendorId()) + ":" + String.format("%04X]", dev.getProductId());
        status.onLinkStatus(text);
        if (!wfbLink.start(wifiChannel, bandWidth.getValue(), dev)) {
            status.onLinkStatus("Could not open wifi adapter " + dev.getDeviceName());
            return false;
        }
        return true;
    }
}
