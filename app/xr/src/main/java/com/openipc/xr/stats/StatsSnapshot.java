package com.openipc.xr.stats;

/**
 * Numbers for the Stats page over the last window (~2 s), immutable. Unknown values: {@link #NA} for ints, NaN for
 * doubles, {@link Segment#NONE} (n = 0) for segments. Formatting belongs to the page.
 *
 * Latency segments, per frame matched by (ssrc, RTP timestamp) between the air's RTP sidecar and the Quest:
 * encode = capture → encoded (air), airSend = encoded → last packet sent (air), link = last packet sent → frame
 * complete on the Quest (air↔Quest clock from the sidecar SYNC), decode = complete → decoded, toDisplay = decoded →
 * next predicted display (an ESTIMATE from the XR display grid, not the compositor latch). total = the per-frame sum:
 * "G2G est." without the sensor readout and the panel.
 */
public final class StatsSnapshot {
    public static final int NA = Integer.MIN_VALUE;
    public static final StatsSnapshot EMPTY = new Builder().build();

    // latency
    public final Segment encode, airSend, link, decode, toDisplay, total;
    public final int matchedFrames;
    public final boolean clockSynced;
    public final double clockRttMs;
    /** Age of the newest sidecar frame; NaN when none arrived (the air segments are then stale or missing). */
    public final double sidecarAgeMs;

    // RX rate: the most frequent one in the window, and its share of the packets
    public final int mcs, nss, bwMhz;
    /** 1 / 0, or NA. */
    public final int sgi, stbc, ldpc;
    public final double rateSharePct;

    // link
    public final int rssiADbm, rssiBDbm, snrADb, snrBDb;
    public final double pDataPct, postFecPct, fecRecPerS, holesPerS;

    // decoder
    public final double fpsDecoded, undecodedPerS;
    public final int decErr;

    // levers
    public final double idrReqOkPerS, idrReqFailedPerS, frozenSlicesPerS;

    // air, from the sidecar trailer
    public final double frameKbP50, pktsPerFrameP50, idrPerS;
    public final int airFillPct;

    private StatsSnapshot(Builder b) {
        encode = b.encode;
        airSend = b.airSend;
        link = b.link;
        decode = b.decode;
        toDisplay = b.toDisplay;
        total = b.total;
        matchedFrames = b.matchedFrames;
        clockSynced = b.clockSynced;
        clockRttMs = b.clockRttMs;
        sidecarAgeMs = b.sidecarAgeMs;
        mcs = b.mcs;
        nss = b.nss;
        bwMhz = b.bwMhz;
        sgi = b.sgi;
        stbc = b.stbc;
        ldpc = b.ldpc;
        rateSharePct = b.rateSharePct;
        rssiADbm = b.rssiADbm;
        rssiBDbm = b.rssiBDbm;
        snrADb = b.snrADb;
        snrBDb = b.snrBDb;
        pDataPct = b.pDataPct;
        postFecPct = b.postFecPct;
        fecRecPerS = b.fecRecPerS;
        holesPerS = b.holesPerS;
        fpsDecoded = b.fpsDecoded;
        undecodedPerS = b.undecodedPerS;
        decErr = b.decErr;
        idrReqOkPerS = b.idrReqOkPerS;
        idrReqFailedPerS = b.idrReqFailedPerS;
        frozenSlicesPerS = b.frozenSlicesPerS;
        frameKbP50 = b.frameKbP50;
        pktsPerFrameP50 = b.pktsPerFrameP50;
        idrPerS = b.idrPerS;
        airFillPct = b.airFillPct;
    }

    public static final class Builder {
        private Segment encode = Segment.NONE, airSend = Segment.NONE, link = Segment.NONE, decode = Segment.NONE,
                toDisplay = Segment.NONE, total = Segment.NONE;
        private int matchedFrames;
        private boolean clockSynced;
        private double clockRttMs = Double.NaN, sidecarAgeMs = Double.NaN;
        private int mcs = NA, nss = NA, bwMhz = NA, sgi = NA, stbc = NA, ldpc = NA;
        private double rateSharePct = Double.NaN;
        private int rssiADbm = NA, rssiBDbm = NA, snrADb = NA, snrBDb = NA;
        private double pDataPct = Double.NaN, postFecPct = Double.NaN, fecRecPerS = Double.NaN,
                holesPerS = Double.NaN;
        private double fpsDecoded = Double.NaN, undecodedPerS = Double.NaN;
        private int decErr = NA;
        private double idrReqOkPerS = Double.NaN, idrReqFailedPerS = Double.NaN, frozenSlicesPerS = Double.NaN;
        private double frameKbP50 = Double.NaN, pktsPerFrameP50 = Double.NaN, idrPerS = Double.NaN;
        private int airFillPct = NA;

        public Builder encode(Segment s) { encode = s; return this; }
        public Builder airSend(Segment s) { airSend = s; return this; }
        public Builder link(Segment s) { link = s; return this; }
        public Builder decode(Segment s) { decode = s; return this; }
        public Builder toDisplay(Segment s) { toDisplay = s; return this; }
        public Builder total(Segment s) { total = s; return this; }

        public Builder matching(int frames, boolean synced, double rttMs, double sidecarAgeMs) {
            matchedFrames = frames;
            clockSynced = synced;
            clockRttMs = rttMs;
            this.sidecarAgeMs = sidecarAgeMs;
            return this;
        }

        public Builder rate(int mcs, int nss, int bwMhz, boolean sgi, boolean stbc, boolean ldpc, double sharePct) {
            this.mcs = mcs;
            this.nss = nss;
            this.bwMhz = bwMhz;
            this.sgi = sgi ? 1 : 0;
            this.stbc = stbc ? 1 : 0;
            this.ldpc = ldpc ? 1 : 0;
            rateSharePct = sharePct;
            return this;
        }

        public Builder rssi(int aDbm, int bDbm) { rssiADbm = aDbm; rssiBDbm = bDbm; return this; }
        public Builder snr(int aDb, int bDb) { snrADb = aDb; snrBDb = bDb; return this; }

        public Builder loss(double pDataPct, double postFecPct, double fecRecPerS, double holesPerS) {
            this.pDataPct = pDataPct;
            this.postFecPct = postFecPct;
            this.fecRecPerS = fecRecPerS;
            this.holesPerS = holesPerS;
            return this;
        }

        public Builder decoder(double fpsDecoded, double undecodedPerS, int decErr) {
            this.fpsDecoded = fpsDecoded;
            this.undecodedPerS = undecodedPerS;
            this.decErr = decErr;
            return this;
        }

        public Builder fpsDecoded(double fps) {
            fpsDecoded = fps;
            return this;
        }

        public Builder undecodedPerS(double perS) {
            undecodedPerS = perS;
            return this;
        }

        /** decErr alone (it comes with the link stats, the decoder fps from elsewhere). */
        public Builder decErr(int decErr) {
            this.decErr = decErr;
            return this;
        }

        public Builder levers(double idrReqOkPerS, double idrReqFailedPerS, double frozenSlicesPerS) {
            this.idrReqOkPerS = idrReqOkPerS;
            this.idrReqFailedPerS = idrReqFailedPerS;
            this.frozenSlicesPerS = frozenSlicesPerS;
            return this;
        }

        public Builder air(double frameKbP50, double pktsPerFrameP50, double idrPerS, int fillPct) {
            this.frameKbP50 = frameKbP50;
            this.pktsPerFrameP50 = pktsPerFrameP50;
            this.idrPerS = idrPerS;
            airFillPct = fillPct;
            return this;
        }

        public StatsSnapshot build() {
            return new StatsSnapshot(this);
        }
    }
}
