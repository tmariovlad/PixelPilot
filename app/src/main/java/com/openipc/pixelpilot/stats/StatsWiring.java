package com.openipc.pixelpilot.stats;

import com.openipc.videonative.VideoPlayer;
import com.openipc.wfbngrtl8812.WfbNgLink;
import com.openipc.xr.XrBridge;

import java.net.InetSocketAddress;
import java.util.function.Supplier;

/**
 * Builds the XR activity's StatsCollector from its live objects. They are read through suppliers on every tick because
 * the activity replaces or nulls them (reattach, teardown); a null one just leaves its fields unknown.
 */
public final class StatsWiring {
    private StatsWiring() {
    }

    public static StatsCollector create(Supplier<VideoPlayer> player, Supplier<WfbNgLink> link,
                                        Supplier<XrBridge> xr) {
        StatsCollector.Inputs inputs = new StatsCollector.Inputs() {
            @Override public long[] drainFrameTimes() {
                VideoPlayer p = player.get();
                return p != null ? p.drainFrameTimes() : null;
            }

            @Override public long[] leverCounters() {
                VideoPlayer p = player.get();
                return p != null ? p.leverCounters() : null;
            }

            @Override public int[] takeRxRate() {
                WfbNgLink l = link.get();
                return l != null ? l.takeRxRate() : null;
            }

            @Override public DisplayEstimate display() {
                XrBridge b = xr.get();
                if (b == null) return null;
                XrBridge.DisplayGrid g = b.displayGrid();
                return GridDisplayEstimate.of(g.displayTimeNs, g.periodNs, g.monotonic);
            }
        };
        StatsCollector[] self = new StatsCollector[1];
        SidecarClient sidecar = new SidecarClient(
                new InetSocketAddress(SidecarClient.AIR_HOST, SidecarClient.AIR_PORT),
                (f, recvUs) -> self[0].onSidecarFrame(f, recvUs), SidecarClient.SUBSCRIBE_MS, SidecarClient.SYNC_MS);
        self[0] = new StatsCollector(inputs, sidecar, StatsCollector.WINDOW_US);
        return self[0];
    }
}
