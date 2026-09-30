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

#endif  // PIXELPILOT_DISPLAYCROP_H
