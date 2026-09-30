#ifndef PIXELPILOT_DISPLAYCROP_H
#define PIXELPILOT_DISPLAYCROP_H

// The picture MediaCodec shows out of a decoded buffer: the output format's crop rect ("crop-left/top/right/bottom",
// inclusive corners) when it is valid, else the whole coded buffer. H.264 codes whole 16-row macroblocks, so 360
// visible rows arrive in a 368-row buffer and 1080 in 1088; the extra rows are encoder padding, and a layer sized to
// the coded height draws them (2026-09-30, O121 S2 stills, docs/xr/link-envelope.md).
struct DisplayCrop
{
    int left = 0, top = 0, width = 0, height = 0;
};

inline DisplayCrop displayCrop(int codedW, int codedH, bool hasCrop, int left, int top, int right, int bottom)
{
    if (hasCrop && left >= 0 && top >= 0 && left <= right && top <= bottom && right < codedW && bottom < codedH)
    {
        return {left, top, right - left + 1, bottom - top + 1};
    }
    return {0, 0, codedW, codedH};
}

// Which output-format keys carry the crop: the Rect key "crop" (AMEDIAFORMAT_KEY_DISPLAY_CROP) first, which is what the
// Quest 2's decoder publishes ("crop: Rect(0, 0, 639, 359)", logcat 2026-09-30), then the four inclusive int keys
// crop-left/top/right/bottom that other decoders publish. getRect(l, t, r, b) and getInt(key, v) wrap AMediaFormat.
template <typename GetRect, typename GetInt>
bool readCropKeys(GetRect getRect, GetInt getInt, int* left, int* top, int* right, int* bottom)
{
    if (getRect(left, top, right, bottom)) return true;
    return getInt("crop-left", left) && getInt("crop-top", top) && getInt("crop-right", right) &&
           getInt("crop-bottom", bottom);
}

#endif  // PIXELPILOT_DISPLAYCROP_H
