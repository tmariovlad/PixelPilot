package com.openipc.videonative;

import androidx.annotation.Keep;

@Keep
public interface IVideoParamsChanged {
    /** The visible picture (the decoder's display crop), not the decoded buffer. */
    void onVideoRatioChanged(int videoW, int videoH);

    /** The decoded buffer the visible picture sits in, and the picture's origin in it (H.264: 360 visible rows in a
     * 368-row buffer, 1080 in 1088). Called right before onVideoRatioChanged. Only the XR layer needs it. */
    default void onVideoCodedSizeChanged(int codedW, int codedH, int cropLeft, int cropTop) {}

    void onDecodingInfoChanged(final DecodingInfo decodingInfo);
}