// DeviceControl (DeviceControl.h): the registry of the RTL devices (per USB fd) and the one lock that sequences every
// control-plane call to them, as devourer's IRtlDevice.h:110-117 asks ("single-control-thread ... never concurrently
// with a channel set").
// - A fake device counts how many calls are inside it at once; the positive control shows the fake does see overlaps
//   when nothing sequences the calls, so a green "0 overlaps" means the lock did it.
// - Lifetime (pixelpilot-xr-25's review, F1/F2): Stop() and the removal happen under the same lock, so no call reaches
//   a stopped or destroyed device, whichever thread (JNI, run, survey) it comes from.
// - The structural test keeps WfbngLink.cpp/.hpp from calling the device directly (bypassing the registry and lock).
#include "DeviceControl.h"

#include <gtest/gtest.h>

#include <atomic>
#include <chrono>
#include <fstream>
#include <memory>
#include <regex>
#include <sstream>
#include <stdexcept>
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
    std::atomic<bool> stopped{false};
    std::atomic<int> afterStop{0};   // control calls that reached the device after its Stop()
    bool stopThrows = false;

    void enter()
    {
        if (stopped) afterStop++;
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
    void StopRxLoop() { enter(); }
    void Stop()
    {
        enter();
        stopped = true;
        if (stopThrows) throw std::runtime_error("usb gone");
    }
};

using Ctl = DeviceControlT<FakeDevice>;
constexpr int kFd = 42;
constexpr int kThreads = 8;
constexpr int kCalls = 100;

template <class Call>
void hammer(Call call)
{
    std::vector<std::thread> ts;
    for (int t = 0; t < kThreads; ++t)
        ts.emplace_back([&call, t] {
            for (int i = 0; i < kCalls; ++i) call((t + i) % 7);
        });
    for (auto& th : ts) th.join();
}
}  // namespace

TEST(DeviceControl, ConcurrentControlCallsNeverOverlapInsideTheDevice)
{
    auto dev = std::make_shared<FakeDevice>();
    Ctl ctl;
    ASSERT_EQ(ctl.attach(kFd, dev), nullptr);
    hammer([&](int op) {
        switch (op)
        {
        case 0: EXPECT_TRUE(ctl.initWrite(kFd, 36)); break;
        case 1: EXPECT_TRUE(ctl.setMonitorChannel(kFd, 40)); break;
        case 2: EXPECT_TRUE(ctl.fastRetune(kFd, 44)); break;
        case 3: EXPECT_TRUE(ctl.setTxPower(kFd, 30)); break;
        case 4: EXPECT_EQ(ctl.rxEnergy(kFd, true), 7); break;
        case 5: EXPECT_TRUE(ctl.stopRxLoop(kFd)); break;
        default: EXPECT_EQ(ctl.selectedChannel(kFd), 36); break;
        }
    });
    EXPECT_EQ(dev->calls.load(), kThreads * kCalls);
    EXPECT_EQ(dev->overlaps.load(), 0);
}

TEST(DeviceControl, PositiveControlTheFakeSeesOverlapsWithoutTheLock)
{
    // Without this, a fake that could never observe an overlap would make the test above pass for nothing.
    FakeDevice dev;
    hammer([&](int op) { op % 2 ? dev.SetTxPower(30) : dev.FastRetune(44); });
    EXPECT_GT(dev.overlaps.load(), 0);
}

TEST(DeviceControl, NoCallReachesADeviceAfterItsStopWhileAnotherThreadKeepsCalling)
{
    // F1/F2: nativeSetTxPower on the JNI thread vs release_link's Stop() + removal on the run thread.
    Ctl ctl;
    std::atomic<bool> done{false};
    std::vector<std::shared_ptr<FakeDevice>> seen;
    std::thread jni([&] {
        while (!done) ctl.setTxPower(kFd, 30);
    });
    for (int round = 0; round < 50; ++round)
    {
        auto dev = std::make_shared<FakeDevice>();
        seen.push_back(dev);
        ASSERT_EQ(ctl.attach(kFd, dev), nullptr);
        std::this_thread::sleep_for(std::chrono::microseconds(300));
        std::string err;
        auto back = ctl.detach(kFd, dev.get(), true, &err);
        EXPECT_EQ(back, dev);   // handed back: the caller destroys it while the USB handle is still valid
        EXPECT_TRUE(err.empty());
    }
    done = true;
    jni.join();
    int after = 0, calls = 0;
    for (const auto& d : seen)
    {
        after += d->afterStop.load();
        calls += d->calls.load();
    }
    EXPECT_EQ(after, 0);
    EXPECT_GT(calls, 50);   // the JNI thread did reach attached devices: the test exercised the race
    EXPECT_FALSE(ctl.setTxPower(kFd, 30));
}

TEST(DeviceControl, CallsForADeviceThatIsNotThereAreNoOps)
{
    Ctl ctl;
    EXPECT_FALSE(ctl.setTxPower(kFd, 30));
    EXPECT_FALSE(ctl.stopRxLoop(kFd));
    EXPECT_EQ(ctl.rxEnergy(kFd, true), 0);
    EXPECT_EQ(ctl.selectedChannel(kFd), 0);
    std::string err;
    EXPECT_EQ(ctl.detach(kFd, nullptr, true, &err), nullptr);
}

TEST(DeviceControl, DevicesArePerFdAndAFailingStopStillDetaches)
{
    // One WfbngLink serves every adapter (WfbNgLink.java: one nativeRun thread per UsbDevice).
    Ctl ctl;
    auto a = std::make_shared<FakeDevice>();
    auto b = std::make_shared<FakeDevice>();
    b->stopThrows = true;
    ASSERT_EQ(ctl.attach(1, a), nullptr);
    ASSERT_EQ(ctl.attach(2, b), nullptr);
    std::string err;
    EXPECT_EQ(ctl.detach(2, b.get(), true, &err), b);
    EXPECT_EQ(err, "usb gone");
    EXPECT_FALSE(ctl.setTxPower(2, 30));
    EXPECT_TRUE(ctl.setTxPower(1, 30));
    EXPECT_EQ(ctl.detach(1, a.get(), false, &err), a);
    EXPECT_FALSE(a->stopped.load());   // stop=false: removed without Stop()
}

TEST(DeviceControl, AttachRefusesAnOccupiedFdAndHandsTheNewDeviceBack)
{
    // A reused fd number while the old run still holds its device (25's hardening note): replacing would free a
    // device another run still uses. The refused device goes back to the caller, which destroys it itself.
    Ctl ctl;
    auto a = std::make_shared<FakeDevice>();
    auto b = std::make_shared<FakeDevice>();
    ASSERT_EQ(ctl.attach(kFd, a), nullptr);
    EXPECT_EQ(ctl.attach(kFd, b), b);
    EXPECT_TRUE(ctl.setTxPower(kFd, 30));
    EXPECT_EQ(a->calls.load(), 1);   // the registered device is still the first one
    EXPECT_EQ(b->calls.load(), 0);
}

TEST(DeviceControl, DetachRemovesOnlyTheDeviceTheCallerAttached)
{
    // The refused run's release_link(fd) must not stop and remove the other run's device on the same fd.
    Ctl ctl;
    auto a = std::make_shared<FakeDevice>();
    auto b = std::make_shared<FakeDevice>();
    ASSERT_EQ(ctl.attach(kFd, a), nullptr);
    std::string err;
    EXPECT_EQ(ctl.detach(kFd, b.get(), true, &err), nullptr);
    EXPECT_EQ(ctl.detach(kFd, nullptr, true, &err), nullptr);   // a run that never attached
    EXPECT_FALSE(a->stopped.load());
    EXPECT_TRUE(ctl.setTxPower(kFd, 30));
    EXPECT_EQ(ctl.detach(kFd, a.get(), true, &err), a);
    EXPECT_TRUE(a->stopped.load());
}

// ---- structural: WfbngLink reaches the device only through DeviceControl ----

namespace
{
// devourer's control-plane entry points (IRtlDevice.h): the TX-power family, channel/width sets, TX mode, CW tone,
// xtal, CCA, register reads, Stop (halts DMA, powers down), plus StopRxLoop (lifetime: the device may be gone).
// StartRxLoop (the run thread's blocking loop on the device it created) and send_packet (TX data path) stay direct.
const std::regex kRawControl(
    R"((->|\.)\s*(InitWrite|SetMonitorChannel|FastRetune|FastSetBandwidth|SetTxPower\w*|ReApplyTxPower|SetXtalCap|)"
    R"(SetTxMode|ClearTxMode|StartCwTone|StopCwTone|SetCcaMode|GetRxEnergy|GetRxQuality|GetSelectedChannel|)"
    R"(Stop|StopRxLoop)\s*\()");

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

void expectNoRawCalls(const char* path)
{
    std::ifstream f(path);
    ASSERT_TRUE(f.good()) << path;
    const auto hits = rawControlCalls(f);
    std::string all;
    for (const auto& h : hits) all += "\n  " + h;
    EXPECT_TRUE(hits.empty()) << path << ": device calls that bypass DeviceControl:" << all;
}
}  // namespace

TEST(DeviceControl, TheScannerFindsRawCallsAndIgnoresCommentsAndTheLockedForm)
{
    std::istringstream bad("dev->SetTxPower(3);\n  rtl_devices.at(fd)->FastRetune(ch);\n"
                           "x->GetRxEnergy(true);\nit->second->Stop();\ndev->StopRxLoop();\n");
    EXPECT_EQ(rawControlCalls(bad).size(), 5u);
    std::istringstream ok("devctl.setTxPower(fd, 3);   // not dev->SetTxPower(3)\n// dev->FastRetune(1);\n"
                          "txFrame->stop();\ndev->StartRxLoop(p);\ndev->send_packet(p, n);\n");
    EXPECT_TRUE(rawControlCalls(ok).empty());
}

TEST(DeviceControl, WfbngLinkMakesNoRawDeviceCall)
{
    expectNoRawCalls(WFBNGLINK_CPP);
    expectNoRawCalls(WFBNGLINK_HPP);
}
