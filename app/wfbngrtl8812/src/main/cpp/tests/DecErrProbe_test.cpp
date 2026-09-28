#include "DecErrProbe.h"

#include <gtest/gtest.h>

using C = DecErrProbe::Counters;

TEST(DecErrProbe, AttributesErrorsToThePacketType) {
    DecErrProbe p;
    p.start(1000);
    p.record(DecErrProbe::kData, C{0, 0, 0}, C{1, 0, 0}, 1010);
    p.record(DecErrProbe::kData, C{1, 0, 0}, C{2, 0, 0}, 1020);
    p.record(DecErrProbe::kSession, C{2, 0, 0}, C{3, 0, 0}, 1030);
    p.record(DecErrProbe::kData, C{3, 0, 0}, C{3, 1, 0}, 1500);        // a good data packet
    p.record(DecErrProbe::kSession, C{3, 1, 0}, C{3, 1, 1}, 1600);     // a good session packet
    const std::string line = p.report(2000);
    EXPECT_NE(line.find("data 2 session 1 other 0"), std::string::npos) << line;
    EXPECT_NE(line.find("ok: data 1 session 1"), std::string::npos) << line;
    EXPECT_NE(line.find("1000 ms after link start (first error 10, last 30, first ok data 500)"), std::string::npos)
        << line;
}

TEST(DecErrProbe, ReportsAtMostOncePerSecond) {
    DecErrProbe p;
    p.start(0);
    p.record(DecErrProbe::kData, C{0, 0, 0}, C{1, 0, 0}, 10);
    EXPECT_EQ("", p.report(999));
    EXPECT_NE("", p.report(1000));
    p.record(DecErrProbe::kData, C{0, 0, 0}, C{1, 0, 0}, 1100);
    EXPECT_EQ("", p.report(1500));                                   // the window restarted at 1000
}

TEST(DecErrProbe, SilentWithoutErrors) {
    DecErrProbe p;
    p.start(0);
    p.record(DecErrProbe::kData, C{0, 0, 0}, C{0, 1, 0}, 10);
    EXPECT_EQ("", p.report(1000));
}

TEST(DecErrProbe, ACounterResetInBetweenIsNotCountedAsErrors) {
    DecErrProbe p;
    p.start(0);
    p.record(DecErrProbe::kData, C{5, 0, 0}, C{0, 1, 0}, 10);         // take_window() ran in between
    EXPECT_EQ("", p.report(1000));
}
