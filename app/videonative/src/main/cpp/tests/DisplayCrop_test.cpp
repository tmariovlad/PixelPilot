// DisplayCrop: the picture MediaCodec shows out of a decoded buffer (the output format's crop rect), not the whole
// coded buffer. H.264 codes whole 16-row macroblocks, so 360 visible rows arrive as 368 and 1080 as 1088; drawing the
// coded height showed the encoder's padding rows at the bottom of the Quest layer (2026-09-30, O121 S2 stills,
// docs/xr/link-envelope.md).
#include "DisplayCrop.h"

#include <gtest/gtest.h>

#include <array>
#include <string>

TEST(DisplayCrop, Res360CropsThePaddingRows)
{
    // the Quest's decoder reported 640x368 on the 480 -> 360 switch; the crop keys are MediaCodec's inclusive corners
    const DisplayCrop c = displayCrop(640, 368, true, 0, 0, 639, 359);
    EXPECT_EQ(c.left, 0);
    EXPECT_EQ(c.top, 0);
    EXPECT_EQ(c.width, 640);
    EXPECT_EQ(c.height, 360);
}

TEST(DisplayCrop, FullHdIs1080Of1088)
{
    const DisplayCrop c = displayCrop(1920, 1088, true, 0, 0, 1919, 1079);
    EXPECT_EQ(c.width, 1920);
    EXPECT_EQ(c.height, 1080);
}

TEST(DisplayCrop, NoCropKeysMeansTheWholeBuffer)
{
    const DisplayCrop c = displayCrop(1280, 720, false, 0, 0, 0, 0);
    EXPECT_EQ(c.left, 0);
    EXPECT_EQ(c.top, 0);
    EXPECT_EQ(c.width, 1280);
    EXPECT_EQ(c.height, 720);
}

TEST(DisplayCrop, AnOffsetCropKeepsItsOrigin)
{
    const DisplayCrop c = displayCrop(640, 480, true, 8, 4, 631, 475);
    EXPECT_EQ(c.left, 8);
    EXPECT_EQ(c.top, 4);
    EXPECT_EQ(c.width, 624);
    EXPECT_EQ(c.height, 472);
}

TEST(DisplayCrop, AnInvalidCropFallsBackToTheWholeBuffer)
{
    // right < left, bottom past the buffer, negative origin: a decoder bug must not draw nothing or read outside
    for (const auto& r : {std::array<int, 4>{10, 0, 5, 359}, std::array<int, 4>{0, 0, 639, 368},
                          std::array<int, 4>{-1, 0, 639, 359}, std::array<int, 4>{0, 0, 640, 359}})
    {
        const DisplayCrop c = displayCrop(640, 368, true, r[0], r[1], r[2], r[3]);
        EXPECT_EQ(c.left, 0);
        EXPECT_EQ(c.top, 0);
        EXPECT_EQ(c.width, 640);
        EXPECT_EQ(c.height, 368);
    }
}

// readCropKeys: which keys carry the crop. The Quest 2's decoder publishes one Rect key, "crop: Rect(0, 0, 639, 359)"
// (logcat 2026-09-30), not the four crop-left/top/right/bottom ints; other decoders publish the ints.
TEST(DisplayCrop, TheRectKeyIsReadFirst)
{
    int        l = -9, t = -9, r = -9, b = -9;
    const bool ok = readCropKeys(
        [](int* a, int* bb, int* c, int* d) { *a = 0; *bb = 0; *c = 639; *d = 359; return true; },
        [](const char*, int*) { return false; }, &l, &t, &r, &b);
    EXPECT_TRUE(ok);
    EXPECT_EQ(r, 639);
    EXPECT_EQ(b, 359);
}

TEST(DisplayCrop, TheIntKeysAreTheFallback)
{
    int        l = -9, t = -9, r = -9, b = -9;
    const bool ok = readCropKeys([](int*, int*, int*, int*) { return false; },
                                 [](const char* key, int* v)
                                 {
                                     const std::string k = key;
                                     *v = k == "crop-right" ? 1919 : k == "crop-bottom" ? 1079 : 0;
                                     return true;
                                 },
                                 &l, &t, &r, &b);
    EXPECT_TRUE(ok);
    EXPECT_EQ(l, 0);
    EXPECT_EQ(r, 1919);
    EXPECT_EQ(b, 1079);
}

TEST(DisplayCrop, NoKeyMeansNoCrop)
{
    int l = 0, t = 0, r = 0, b = 0;
    EXPECT_FALSE(readCropKeys([](int*, int*, int*, int*) { return false; }, [](const char*, int*) { return false; }, &l,
                              &t, &r, &b));
    // one int key missing is no crop either
    EXPECT_FALSE(readCropKeys([](int*, int*, int*, int*) { return false; },
                              [](const char* key, int* v) { *v = 1; return std::string(key) != "crop-top"; }, &l, &t,
                              &r, &b));
}
