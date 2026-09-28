package com.openipc.pixelpilot;

import com.openipc.xr.PresetCatalog;
import com.openipc.xr.PresetMenu;
import com.openipc.xr.PresetStatus;

import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.function.Consumer;
import java.util.function.IntFunction;

/**
 * The app's side of a preset change (docs/xr/presets-design.md): turns the menu's confirmed actions into VMODE1
 * requests, follows the air unit's replies and state beacon, confirms a mode switch once the new video decodes
 * ({@link CommitGate}), and keeps the headline ({@link PresetStatus}). The air owns the presets and the revert timer;
 * this class only asks and reports. UI thread only: the transport's callbacks must be posted here.
 */
final class VmodeSession implements VmodeClient.Listener {
    /** Seconds the air waits for our commit before it reverts: c8's 10-14 s to a stable encoder plus margin. */
    static final int REVERT_S = 25;
    /** The air forgets a requester it has not heard from; a list at least this often keeps its beacon coming. */
    static final long LIST_KEEPALIVE_MS = 60_000;

    private final VmodeSender sender;
    private final Consumer<PresetCatalog> onCatalog;
    private final PresetStatus status = new PresetStatus();
    private final CommitGate gate = new CommitGate();
    private final Map<Integer, String> requests = new HashMap<>();   // seq -> verb, for acks
    private PresetCatalog catalog;
    private boolean listing;
    private String applyMode;          // the last apply: mode (null = unchanged) and kbps (0 = unchanged)
    private int applyKbps;
    private int effectiveKbps;
    private long nowMs;
    private long lastListMs = Long.MIN_VALUE / 2;
    private boolean ticked;          // the first list goes out before the first tick, i.e. before the clock is known

    VmodeSession(VmodeSender sender, Consumer<PresetCatalog> onCatalog) {
        this.sender = sender;
        this.onCatalog = onCatalog;
    }

    /** Asks the air for its presets unless a list is known or on its way (at start and when the menu opens). */
    void ensureList() {
        if (catalog != null || listing) return;
        list();
    }

    private void list() {
        listing = true;
        lastListMs = nowMs;
        send("list", VmodeProtocol::list);
    }

    /** A confirmed menu action. */
    void apply(PresetMenu.Action a) {
        if (catalog == null) return;
        if (a.saveDefault) {
            send("save_default", VmodeProtocol::saveDefault);
            return;
        }
        applyMode = a.mode;
        applyKbps = a.kbps;
        send("apply", seq -> VmodeProtocol.apply(seq, a.mode, a.kbps, REVERT_S));
    }

    /** Once per stats tick: frames decoded since the last tick and the current video size. */
    void tick(long nowMs, int frames, int w, int h) {
        this.nowMs = nowMs;
        if (!ticked) {
            ticked = true;
            lastListMs = nowMs;      // count the keepalive from here, not from the unknown time of the first list
        }
        if (!listing && nowMs - lastListMs >= LIST_KEEPALIVE_MS) list();
        String token = gate.onFrames(frames, w, h);
        if (token != null) send("commit", seq -> VmodeProtocol.commit(seq, token));
    }

    String headline() {
        return status.headline(nowMs);
    }

    /** True while a mode switch runs: the frozen picture is expected, so this headline wins over NO SIGNAL. */
    boolean switching() {
        return status.switching();
    }

    /** For the video line: active preset and effective bitrate, "" before the air answered. */
    String videoSuffix() {
        if (catalog == null) return "";
        int i = catalog.modeIndex(catalog.activeMode);
        String label = i >= 0 ? catalog.modes.get(i).label : catalog.activeMode;
        if (effectiveKbps <= 0) return "  " + label;
        boolean capped = catalog.requestedKbps > 0 && effectiveKbps < catalog.requestedKbps;
        return String.format(Locale.US, "  %s %.1f Mbit%s", label, effectiveKbps / 1000.0, capped ? " (capped)" : "");
    }

    @Override
    public void onReply(VmodeProtocol.Reply r) {
        String sent = r.seq() >= 0 ? requests.remove(r.seq()) : null;
        switch (r.verb) {
            case "list":
                listing = false;
                setCatalog(VmodeProtocol.catalog(r));
                break;
            case "ack":
                onAck(sent, r);
                break;
            case "state":
                onState(r);
                break;
            default:
                break;
        }
    }

    @Override
    public void onNoReply(String verb) {
        if ("list".equals(verb)) listing = false;
        else if ("apply".equals(verb) || "save_default".equals(verb)) status.refused("no reply from air", nowMs);
        // a lost commit needs nothing here: the air reverts by itself and its beacon says so
    }

    private void onAck(String verb, VmodeProtocol.Reply r) {
        String state = r.field("state");
        if ("busy".equals(state)) {
            status.refused("air busy", nowMs);
        } else if ("error".equals(state)) {
            status.refused(r.field("reason"), nowMs);
            gate.clear();
        } else if ("apply".equals(verb) && "accepted".equals(state) && applyMode != null) {
            PresetCatalog.Mode m = catalog.modes.get(Math.max(0, catalog.modeIndex(applyMode)));
            int[] size = m.encodeSize();
            gate.expect(r.field("token"), size[0], size[1]);
            status.switching(m.label, nowMs + REVERT_S * 1000L);
        } else if ("committed".equals(state)) {
            String mode = applyMode != null ? applyMode : catalog.activeMode;
            int kbps = applyKbps > 0 ? applyKbps : catalog.requestedKbps;
            setCatalog(catalog.withActive(mode, kbps));
            status.done(applyMode != null ? label(mode) : PresetMenu.mbit(kbps) + "/s", nowMs);
        } else if ("saved".equals(state)) {
            status.saved(label(catalog.activeMode), nowMs);
        }
    }

    private void onState(VmodeProtocol.Reply r) {
        effectiveKbps = r.intField("kbps", effectiveKbps);
        String phase = r.field("phase");
        if ("pending".equals(phase)) gate.arm(r.field("token"));
        if (("reverting".equals(phase) || "failed".equals(phase) || "reverted".equals(phase)) && status.switching()) {
            gate.clear();
            status.reverted(label(r.field("preset")), nowMs);
        }
        if (catalog == null) return;
        String mode = r.field("preset");
        int req = r.intField("req_kbps", catalog.requestedKbps);
        if (!mode.isEmpty() && !status.switching() && (!mode.equals(catalog.activeMode) || req != catalog.requestedKbps)) {
            setCatalog(catalog.withActive(mode, req));
        }
    }

    private void setCatalog(PresetCatalog c) {
        catalog = c;
        onCatalog.accept(c);
    }

    private String label(String mode) {
        int i = catalog == null ? -1 : catalog.modeIndex(mode);
        return i >= 0 ? catalog.modes.get(i).label : mode;
    }

    private void send(String verb, IntFunction<String> build) {
        requests.put(sender.request(verb, build), verb);
    }
}
