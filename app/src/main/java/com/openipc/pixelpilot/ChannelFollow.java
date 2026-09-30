package com.openipc.pixelpilot;

import java.util.Arrays;
import java.util.HashSet;
import java.util.Locale;
import java.util.Set;
import java.util.function.Consumer;

/**
 * O123 rule 1: the air's channel is the truth, the app's stored channel follows it. A VMODE1 state beacon names the
 * channel the air is on ({@code ch=}, EXT beacons only). When it is legal, settled and differs from the stored
 * channel, the stored channel is updated and logged. Nothing is sent to the air and the radio is not touched: over
 * the default wfb target (VmodeClient.AIR_RECEIVER) a beacon heard at all means the RTL already listens on that
 * channel, so only the stored value was stale (it is what the next link start tunes to). With a LAN target
 * (the vmode_air debug pref) beacons arrive whatever the RTL is tuned to, and a channel picked by hand is replaced
 * by the next settled beacon: the air is the truth.
 * <p>
 * Not stored: an announced switch ({@code ch_to=}), a phase in which the air may still move (applying / pending /
 * reverting: no commit within revert_s sends it back), failed (a failed channel revert leaves vmoded's ch at the
 * switch target, not a verified channel: sw_chan.c TX_REV_WFB -> ext_failed), a v1 beacon without {@code ch=}, an illegal channel, and
 * anything that is not a state beacon. UI thread only, like {@link VmodeSession}.
 */
final class ChannelFollow {
    /** The app's stored channel (the "wifi-channel" preference). */
    interface Store {
        int channel();

        void setChannel(int ch);
    }

    /**
     * vmoded's phases (sm.c vm_phase_str: ok | applying | pending | reverting | reverted | failed) whose ch= is a
     * verified channel that will not change without a new request.
     */
    private static final Set<String> SETTLED = new HashSet<>(Arrays.asList("ok", "reverted"));

    private final Store store;
    private final Consumer<String> log;

    ChannelFollow(Store store, Consumer<String> log) {
        this.store = store;
        this.log = log;
    }

    /** True when the stored channel was changed. */
    boolean onReply(VmodeProtocol.Reply r) {
        if (r == null || !"state".equals(r.verb)) return false;
        if (!r.field("ch_to").isEmpty() || !SETTLED.contains(r.field("phase"))) return false;
        int ch = r.intField("ch", 0);
        if (!LegalChannels.isLegal(ch)) return false;
        int stored = store.channel();
        if (ch == stored) return false;
        store.setChannel(ch);
        log.accept(String.format(Locale.US, "channel: stored %d -> %d (air beacon)", stored, ch));
        return true;
    }
}
