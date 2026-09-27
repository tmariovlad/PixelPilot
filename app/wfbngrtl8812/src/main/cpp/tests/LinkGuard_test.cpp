#include "LinkGuard.h"

#include <gtest/gtest.h>

#include <stdexcept>
#include <string>
#include <vector>

namespace {
struct Logged {
    std::vector<std::string> what;
    void operator()(const char *, const char *w) { what.emplace_back(w); }
};
}  // namespace

TEST(LinkGuard, NormalReturnPassesThroughWithoutLogging) {
    Logged log;
    EXPECT_EQ(0, run_guarded([] { return 0; }, log));
    EXPECT_EQ(-7, run_guarded([] { return -7; }, log));
    EXPECT_TRUE(log.what.empty());
}

TEST(LinkGuard, RuntimeErrorBecomesMinusOne) {
    Logged log;
    EXPECT_EQ(-1, run_guarded([]() -> int { throw std::runtime_error("rx failed"); }, log));
    ASSERT_EQ(1u, log.what.size());
    EXPECT_EQ("rx failed", log.what[0]);
}

TEST(LinkGuard, LogicErrorFromDevourerIsCaughtToo) {
    // the old catch only took std::runtime_error, so this one reached std::terminate
    Logged log;
    EXPECT_EQ(-1, run_guarded([]() -> int { throw std::logic_error("efuse"); }, log));
    EXPECT_EQ("efuse", log.what.at(0));
}

TEST(LinkGuard, NonStdExceptionIsCaught) {
    Logged log;
    EXPECT_EQ(-1, run_guarded([]() -> int { throw 42; }, log));
    EXPECT_EQ("non-std exception", log.what.at(0));
}
