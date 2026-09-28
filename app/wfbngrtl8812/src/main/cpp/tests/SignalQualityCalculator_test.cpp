#include "SignalQualityCalculator.h"

#include <gtest/gtest.h>

TEST(SignalQualityCalculator, AveragesEachReceiveChainSeparately) {
    SignalQualityCalculator c;
    c.add_rssi(60, 40);
    c.add_rssi(70, 50);
    c.add_snr(20, -4);
    c.add_snr(30, -6);

    auto q = c.calculate_signal_quality();

    EXPECT_FLOAT_EQ(65.f, q.rssi_chains.ant1);
    EXPECT_FLOAT_EQ(45.f, q.rssi_chains.ant2);
    EXPECT_FLOAT_EQ(25.f, q.snr_chains.ant1);
    EXPECT_FLOAT_EQ(-5.f, q.snr_chains.ant2);
    // The combined values still come from the better chain: SNR max, RSSI 65 of 0..80 mapped to -1024..1024.
    EXPECT_FLOAT_EQ(25.f, q.snr);
    EXPECT_EQ(640, q.quality);
}

TEST(SignalQualityCalculator, BetterChainCanBeEitherAntenna) {
    SignalQualityCalculator c;
    c.add_rssi(30, 62);
    c.add_snr(4, 28);

    auto q = c.calculate_signal_quality();

    EXPECT_FLOAT_EQ(30.f, q.rssi_chains.ant1);
    EXPECT_FLOAT_EQ(62.f, q.rssi_chains.ant2);
    EXPECT_FLOAT_EQ(28.f, q.snr);
}

TEST(SignalQualityCalculator, NoSamplesGivesZeroPerChain) {
    SignalQualityCalculator c;

    auto q = c.calculate_signal_quality();

    EXPECT_FLOAT_EQ(0.f, q.rssi_chains.ant1);
    EXPECT_FLOAT_EQ(0.f, q.rssi_chains.ant2);
    EXPECT_FLOAT_EQ(0.f, q.snr_chains.ant1);
    EXPECT_FLOAT_EQ(0.f, q.snr_chains.ant2);
}
