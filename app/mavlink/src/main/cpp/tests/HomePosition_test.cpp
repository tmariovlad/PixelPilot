#include "HomePosition.h"

#include <gtest/gtest.h>

TEST(HomePosition, SetOnceWhenArmedWithAFix) {
    HomePosition h;
    h.update(true, 3, 100, 200);
    ASSERT_TRUE(h.set);
    h.update(true, 3, 150, 250);                     // the aircraft moved: home stays put
    EXPECT_EQ(100, h.lat);
    EXPECT_EQ(200, h.lon);
}

TEST(HomePosition, NotSetBeforeArming) {
    HomePosition h;
    h.update(false, 3, 100, 200);
    EXPECT_FALSE(h.set);
}

TEST(HomePosition, ArmedWithoutAFixWaitsForTheFirstFix) {
    HomePosition h;
    h.update(true, 0, 0, 0);
    EXPECT_FALSE(h.set);                              // no (0,0) home
    h.update(true, 3, 100, 200);
    ASSERT_TRUE(h.set);
    EXPECT_EQ(100, h.lat);
}

TEST(HomePosition, DisarmForgetsItAndTheNextArmingSetsANewOne) {
    HomePosition h;
    h.update(true, 3, 100, 200);
    h.update(false, 3, 300, 400);
    EXPECT_FALSE(h.set);
    h.update(true, 3, 300, 400);
    EXPECT_EQ(300, h.lat);
}
