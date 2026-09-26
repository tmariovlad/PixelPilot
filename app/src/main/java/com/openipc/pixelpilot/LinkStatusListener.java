package com.openipc.pixelpilot;

/** Where WfbLinkManager reports link state, so it does not depend on a particular UI. */
public interface LinkStatusListener {
    /** One-line status, e.g. "Starting wfb-ng channel 161 with [0BDA:8812]". */
    void onLinkStatus(String message);

    /** No usable adapter; a stream can still be pushed over wifi to this udp:// address. */
    void onUdpFallbackAddress(String udpUrl);
}
