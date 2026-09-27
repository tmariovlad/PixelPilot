#include "DecoderRecovery.h"

#include <gtest/gtest.h>

TEST(DecoderRecovery, AFailedConfigureWaitsForTheNextKeyFrame) {
    DecoderRecovery r;
    EXPECT_TRUE(r.configureFailed(false, true));       // window present, nothing configured: failure
    EXPECT_EQ(" | cfg-fail 1", r.summary());
}

TEST(DecoderRecovery, NoWindowYetIsNotAFailure) {
    DecoderRecovery r;
    EXPECT_FALSE(r.configureFailed(false, false));
    EXPECT_FALSE(r.configureFailed(true, true));
    EXPECT_EQ("", r.summary());
}

TEST(DecoderRecovery, AnOutputFailureRebuildsOnce) {
    DecoderRecovery r;
    r.outputFailed(0);
    EXPECT_TRUE(r.shouldRebuild(0, true));
    EXPECT_FALSE(r.shouldRebuild(0, true));             // flag consumed
    EXPECT_EQ(" | rebuilt 1", r.summary());
}

TEST(DecoderRecovery, AnUnconfiguredDecoderIsNotRebuilt) {
    DecoderRecovery r;
    r.outputFailed(1);
    EXPECT_FALSE(r.shouldRebuild(1, false));
}

TEST(DecoderRecovery, ConfiguringClearsAFlagLeftByARelease) {
    // releaseDecoder stops the codec, so its output loop exits and flags; a fresh decoder must start clean
    DecoderRecovery r;
    r.outputFailed(0);
    r.configured(0);
    EXPECT_FALSE(r.shouldRebuild(0, true));
}

TEST(DecoderRecovery, DecodersAreIndependent) {
    DecoderRecovery r;
    r.outputFailed(1);
    EXPECT_FALSE(r.shouldRebuild(0, true));
    EXPECT_TRUE(r.shouldRebuild(1, true));
}
