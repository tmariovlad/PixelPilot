package com.openipc.pixelpilot;

import java.util.Collection;
import java.util.HashSet;
import java.util.Set;

/**
 * Asks for USB permission at most once per adapter attachment (audit X14).
 *
 * <p>The permission result broadcast is lost while the activity is paused (the receiver is unregistered, and the
 * system dialog itself pauses the activity), so a denial cannot be observed reliably. Asking again on every resume
 * then loops as long as the user keeps saying no. Instead: ask once, and ask again only after the adapter has been
 * unplugged (it is no longer attached) and plugged back in. Shared by the 2D and XR activities.
 */
final class UsbPermissionGate {
    private final Set<String> asked = new HashSet<>();

    /** @return true if permission should be requested for {@code device} now */
    synchronized boolean shouldAsk(String device) {
        return asked.add(device);
    }

    /** Forgets adapters that are no longer attached, so a replug asks again. */
    synchronized void retainAttached(Collection<String> attachedDevices) {
        asked.retainAll(attachedDevices);
    }
}
