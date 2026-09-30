// DisplayCrop: the picture MediaCodec shows out of a decoded buffer (the output format's crop rect), not the whole
// coded buffer. H.264 codes whole 16-row macroblocks, so 360 visible rows arrive as 368 and 1080 as 1088; drawing the
// coded height showed the encoder's padding rows at the bottom of the Quest layer (2026-09-30, O121 S2 stills,
// docs/xr/link-envelope.md).
#include "DisplayCrop.h"

#include <gtest/gtest.h>

#include <array>

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
