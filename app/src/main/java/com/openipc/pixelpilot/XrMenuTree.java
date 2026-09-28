package com.openipc.pixelpilot;

import static com.openipc.videonative.LatencyExperiments.*;

import com.openipc.xr.menu.ApplyClass;
import com.openipc.xr.menu.MenuItem;
import com.openipc.xr.menu.MenuNavigator;
import com.openipc.xr.menu.StatsPages;

/**
 * What the in-headset menu offers (docs/xr/menu-design.md §5): the one place that lists its folders, pages and
 * options. Quest options use the {@link com.openipc.videonative.LatencyExperiments} pref keys as their ids; air options
 * use {@code air.*} ids that the model maps to the VMODE1 catalog. Values live in {@link XrMenuModel}.
 */
final class XrMenuTree {
    static final String AIR_MODE = "air.mode";
    static final String AIR_QUALITY = "air.quality";
    static final String AIR_MCS = "air.mcs";
    static final String AIR_FEC = "air.fec";
    static final String AIR_STREAMS = "air.streams";
    static final String AIR_TXPOWER = "air.txpower";
    static final String AIR_ALINK = "air.alink";
    static final String AIR_CODEC = "air.codec";
    static final String AIR_CHANNEL = "air.channel";
    static final String PANEL_DETAIL = "panel.detail";
    static final String RESET_QUEST = "reset.quest";

    private XrMenuTree() {
    }

    static MenuItem build() {
        return MenuItem.folder("root", "Menu",
                MenuItem.folder("stats", "Stats",
                        MenuItem.page(StatsPages.SUMMARY, "Summary"),
                        MenuItem.page(StatsPages.LATENCY, "Latency"),
                        MenuItem.page(StatsPages.LINK, "Link"),
                        MenuItem.page(StatsPages.LEVERS, "Levers")),
                MenuItem.folder("picture", "Picture",
                        MenuItem.bool(KEY_FEED_INCOMPLETE_FRAMES, "Feed incomplete", ApplyClass.LIVE),
                        MenuItem.bool(KEY_REQUEST_IDR_ON_LOSS, "Keyframe on loss", ApplyClass.LIVE),
                        MenuItem.choice(KEY_IDR_MIN_INTERVAL_MS, "Keyframe interval", ApplyClass.LIVE),
                        MenuItem.bool(KEY_FREEZE_UNTIL_IDR, "Freeze until IDR", ApplyClass.LIVE),
                        MenuItem.bool(KEY_RTP_TIGHT_REORDER, "Tight reorder", ApplyClass.LIVE),
                        MenuItem.folder("decoder", "Decoder",
                                MenuItem.bool(KEY_LOW_LATENCY_DECODER, "Low-latency keys", ApplyClass.RELAUNCH),
                                MenuItem.bool(KEY_DEC_PICTURE_ORDER, "Picture order", ApplyClass.RELAUNCH),
                                MenuItem.bool(KEY_DEC_OPERATING_RATE, "Operating rate", ApplyClass.RELAUNCH),
                                MenuItem.bool(KEY_DEC_PREFER_LOW_LATENCY_COMPONENT, "LL component",
                                        ApplyClass.RELAUNCH),
                                MenuItem.bool(KEY_AU_AGGREGATION, "AU aggregation", ApplyClass.RELAUNCH))),
                MenuItem.folder("air", "Air",
                        MenuItem.choice(AIR_MODE, "Mode", ApplyClass.AIR),
                        MenuItem.choice(AIR_QUALITY, "Quality kbit/s", ApplyClass.AIR),
                        MenuItem.folder("radio", "Radio",
                                MenuItem.choice(AIR_MCS, "MCS", ApplyClass.AIR),
                                MenuItem.choice(AIR_FEC, "FEC k/n", ApplyClass.AIR),
                                MenuItem.choice(AIR_STREAMS, "Streams", ApplyClass.AIR),
                                MenuItem.choice(AIR_TXPOWER, "TX power dBm", ApplyClass.AIR),
                                MenuItem.bool(AIR_ALINK, "Adaptive link", ApplyClass.AIR)),
                        MenuItem.choice(AIR_CODEC, "Codec", ApplyClass.AIR),
                        MenuItem.choice(AIR_CHANNEL, "Channel", ApplyClass.AIR_AND_QUEST)),
                MenuItem.folder("display", "Display",
                        MenuItem.choice(KEY_XR_REFRESH_HZ, "Refresh Hz", ApplyClass.RELAUNCH),
                        MenuItem.number(KEY_XR_FOV_DEG, "Field of view", ApplyClass.LIVE, (int) MIN_FOV_DEG,
                                (int) MAX_FOV_DEG, 5, "deg"),
                        MenuItem.choice(KEY_XR_LAYER_SHAPE, "Shape", ApplyClass.LIVE),
                        MenuItem.bool(KEY_XR_FLIP_VERTICAL, "Flip vertical", ApplyClass.LIVE),
                        MenuItem.bool(KEY_XR_USE_TIMESTAMPS, "Timestamps", ApplyClass.RELAUNCH),
                        MenuItem.bool(KEY_XR_PERF_SUSTAINED_HIGH, "Perf high", ApplyClass.RELAUNCH),
                        MenuItem.bool(KEY_XR_THREAD_HINTS, "Thread hints", ApplyClass.RELAUNCH)),
                MenuItem.folder("panel", "Panel",
                        MenuItem.choice(PANEL_DETAIL, "Stats panel", ApplyClass.LIVE)),
                MenuItem.folder("reset", "Save / reset",
                        MenuItem.action(RESET_QUEST, "Quest to defaults")),
                MenuItem.action(MenuNavigator.CLOSE_ID, "Close"));
    }
}
