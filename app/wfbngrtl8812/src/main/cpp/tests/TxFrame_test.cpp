// Host tests for TxFrame's lifecycle, run over real UDP sockets with the UdpTransmitter (debug_port) path, so no
// USB device is needed. Background (2026-09-27): every link restart on the Quest left one more socket bound to
// UDP 8001 and the uplink dead, because WfbngLink reused a stopped TxFrame and run() never closed its socket.
#include "TxFrame.h"

#include <gtest/gtest.h>
#include <sodium.h>

#include <arpa/inet.h>
#include <chrono>
#include <cstdio>
#include <dirent.h>
#include <netinet/in.h>
#include <poll.h>
#include <string>
#include <sys/socket.h>
#include <thread>
#include <unistd.h>

namespace {
constexpr int kInPort = 38001;   // TxFrame listens here (the app uses 8001)
constexpr int kOutPort = 38002;  // UdpTransmitter sends the wfb frames here

int openFdCount() {
    int n = 0;
    DIR *d = opendir("/proc/self/fd");
    while (readdir(d) != nullptr) n++;
    closedir(d);
    return n;
}

std::string writeKeyFile() {
    unsigned char txSecret[crypto_box_SECRETKEYBYTES], txPublic[crypto_box_PUBLICKEYBYTES];
    unsigned char rxSecret[crypto_box_SECRETKEYBYTES], rxPublic[crypto_box_PUBLICKEYBYTES];
    crypto_box_keypair(txPublic, txSecret);
    crypto_box_keypair(rxPublic, rxSecret);
    std::string path = "/tmp/txframe_test.key";
    FILE *f = std::fopen(path.c_str(), "wb");
    std::fwrite(txSecret, sizeof txSecret, 1, f);  // same layout as a wfb-ng drone.key / gs.key
    std::fwrite(rxPublic, sizeof rxPublic, 1, f);
    std::fclose(f);
    return path;
}

TxArgs testArgs() {
    TxArgs a;
    a.udp_port = kInPort;
    a.debug_port = kOutPort;
    a.keypair = writeKeyFile();
    a.k = 1;
    a.n = 2;
    a.log_interval = 100;
    return a;
}

int udpSocket(int bindPort) {
    int fd = ::socket(AF_INET, SOCK_DGRAM, 0);
    if (bindPort) {
        sockaddr_in a{};
        a.sin_family = AF_INET;
        a.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
        a.sin_port = htons(bindPort);
        ::bind(fd, reinterpret_cast<sockaddr *>(&a), sizeof a);
    }
    return fd;
}

// Sends one packet to TxFrame's input port every 50 ms until a frame shows up on the output port.
bool forwardsWithin(std::chrono::milliseconds limit) {
    int out = udpSocket(kOutPort);
    int in = udpSocket(0);
    sockaddr_in dst{};
    dst.sin_family = AF_INET;
    dst.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    dst.sin_port = htons(kInPort);
    const char payload[] = "uplink";
    bool got = false;
    auto end = std::chrono::steady_clock::now() + limit;
    while (!got && std::chrono::steady_clock::now() < end) {
        ::sendto(in, payload, sizeof payload, 0, reinterpret_cast<sockaddr *>(&dst), sizeof dst);
        pollfd p{out, POLLIN, 0};
        got = ::poll(&p, 1, 50) > 0;
    }
    ::close(in);
    ::close(out);
    return got;
}
}  // namespace

class TxFrameLifecycle : public ::testing::Test {
  protected:
    static void SetUpTestSuite() { ASSERT_GE(sodium_init(), 0); }
};

TEST_F(TxFrameLifecycle, RunClosesItsUdpSocketWhenStopped) {
    TxArgs args = testArgs();
    const int before = openFdCount();
    TxFrame tx;
    std::thread t([&] { tx.run(nullptr, &args); });
    ASSERT_TRUE(forwardsWithin(std::chrono::milliseconds(3000)));  // running, socket bound
    tx.stop();
    t.join();
    EXPECT_EQ(before, openFdCount()) << "run() left a file descriptor open (the UDP input socket)";
}

TEST_F(TxFrameLifecycle, AFreshInstanceForwardsAfterARestart) {
    TxArgs args = testArgs();
    {
        TxFrame first;
        std::thread t([&] { first.run(nullptr, &args); });
        ASSERT_TRUE(forwardsWithin(std::chrono::milliseconds(3000)));
        first.stop();
        t.join();
    }
    TxFrame second;  // what WfbngLink now does on every TX thread start
    std::thread t([&] { second.run(nullptr, &args); });
    EXPECT_TRUE(forwardsWithin(std::chrono::milliseconds(3000))) << "restarted uplink does not forward";
    second.stop();
    t.join();
}

TEST_F(TxFrameLifecycle, StopIsFinalForAnInstance) {
    // This is why WfbngLink must not reuse a stopped TxFrame: run() on it returns at once and forwards nothing.
    TxArgs args = testArgs();
    TxFrame tx;
    tx.stop();
    auto t0 = std::chrono::steady_clock::now();
    std::thread t([&] { tx.run(nullptr, &args); });
    t.join();
    EXPECT_LT(std::chrono::steady_clock::now() - t0, std::chrono::milliseconds(1500));
}
