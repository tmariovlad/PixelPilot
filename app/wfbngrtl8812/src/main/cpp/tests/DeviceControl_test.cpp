// DeviceControl (DeviceControl.h): every control-plane call to the RTL is sequenced by one lock, as devourer's
// IRtlDevice.h:110-117 asks ("single-control-thread ... never concurrently with a channel set"). A fake device counts
// how many calls are inside it at once; the positive control shows the fake does see overlaps when nothing sequences
// the calls, so a green "0 overlaps" means the lock did it. The structural test keeps WfbngLink.cpp from calling a
// control-plane method on the device directly (bypassing the lock).
#include "DeviceControl.h"

#include <gtest/gtest.h>

#include <atomic>
#include <chrono>
#include <fstream>
#include <regex>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

namespace
{
struct FakeDevice
{
    std::atomic<int> inside{0};
    std::atomic<int> overlaps{0};
    std::atomic<int> calls{0};

    void enter()
    {
        if (++inside > 1) overlaps++;
        calls++;
        std::this_thread::sleep_for(std::chrono::microseconds(50));
        --inside;
    }
    void InitWrite(int) { enter(); }
    void SetMonitorChannel(int) { enter(); }
    void FastRetune(uint8_t) { enter(); }
    void SetTxPower(uint8_t) { enter(); }
    int GetRxEnergy(bool)
    {
        enter();
        return 7;
    }
    int GetSelectedChannel()
    {
        enter();
        return 36;
    }
};

constexpr int kThreads = 8;
constexpr int kCalls = 100;

template <class Call>
void hammer(Call call)
{
    std::vector<std::thread> ts;
    for (int t = 0; t < kThreads; ++t)
        ts.emplace_back([&call, t] {
            for (int i = 0; i < kCalls; ++i) call((t + i) % 6);
        });
    for (auto& th : ts) th.join();
}
}  // namespace

TEST(DeviceControl, ConcurrentControlCallsNeverOverlapInsideTheDevice)
{
    FakeDevice dev;
    DeviceControlT<FakeDevice> ctl;
    hammer([&](int op) {
        switch (op)
        {
        case 0: ctl.initWrite(&dev, 36); break;
        case 1: ctl.setMonitorChannel(&dev, 40); break;
        case 2: ctl.fastRetune(&dev, 44); break;
        case 3: ctl.setTxPower(&dev, 30); break;
        case 4: EXPECT_EQ(ctl.rxEnergy(&dev, true), 7); break;
        default: EXPECT_EQ(ctl.selectedChannel(&dev), 36); break;
        }
    });
    EXPECT_EQ(dev.calls.load(), kThreads * kCalls);
    EXPECT_EQ(dev.overlaps.load(), 0);
}

TEST(DeviceControl, PositiveControlTheFakeSeesOverlapsWithoutTheLock)
{
    // Without this, a fake that could never observe an overlap would make the test above pass for nothing.
    FakeDevice dev;
    hammer([&](int op) { op % 2 ? dev.SetTxPower(30) : dev.FastRetune(44); });
    EXPECT_GT(dev.overlaps.load(), 0);
}

// ---- structural: WfbngLink.cpp reaches the device's control plane only through DeviceControl ----

namespace
{
// devourer's control-plane entry points (IRtlDevice.h): the TX-power family, channel/width sets, TX mode, CW tone,
// xtal, CCA, energy/quality reads that touch registers. StartRxLoop / StopRxLoop / send_packet are not control-plane
// calls here (DeviceControl.h says why).
const std::regex kRawControl(
    R"((->|\.)\s*(InitWrite|SetMonitorChannel|FastRetune|FastSetBandwidth|SetTxPower\w*|ReApplyTxPower|SetXtalCap|)"
    R"(SetTxMode|ClearTxMode|StartCwTone|StopCwTone|SetCcaMode|GetRxEnergy|GetRxQuality|GetSelectedChannel)\s*\()");

std::vector<std::string> rawControlCalls(std::istream& in)
{
    std::vector<std::string> hits;
    std::string line;
    for (int n = 1; std::getline(in, line); ++n)
    {
        const auto c = line.find("//");
        const std::string code = c == std::string::npos ? line : line.substr(0, c);
        if (std::regex_search(code, kRawControl)) hits.push_back(std::to_string(n) + ": " + line);
    }
    return hits;
}
}  // namespace

TEST(DeviceControl, TheScannerFindsRawCallsAndIgnoresCommentsAndTheLockedForm)
{
    std::istringstream bad("dev->SetTxPower(3);\n  rtl_devices.at(fd)->FastRetune(ch);\n"
                           "x->GetRxEnergy(true);\n");
    EXPECT_EQ(rawControlCalls(bad).size(), 3u);
    std::istringstream ok("devctl.setTxPower(dev, 3);   // not dev->SetTxPower(3)\n// dev->FastRetune(1);\n"
                          "dev->StopRxLoop();\ndev->send_packet(p, n);\n");
    EXPECT_TRUE(rawControlCalls(ok).empty());
}

TEST(DeviceControl, WfbngLinkMakesNoRawControlPlaneCall)
{
    std::ifstream f(WFBNGLINK_CPP);
    ASSERT_TRUE(f.good()) << WFBNGLINK_CPP;
    const auto hits = rawControlCalls(f);
    std::string all;
    for (const auto& h : hits) all += "\n  " + h;
    EXPECT_TRUE(hits.empty()) << "device control-plane calls that bypass DeviceControl:" << all;
}
