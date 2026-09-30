// wfb-ng's rx Aggregator, fed real encrypted k=4/n=8 packets from our Transmitter (TxFrame.cpp) in chosen orders:
// when the front FEC block completes, the next block's fragments that already arrived in order must be released in
// the same call, not held until one more of its fragments arrives (openipc O121 finding N3, pixelpilot-xr-4b;
// docs/xr/fec-block-probe.md §8).
#include "TxFrame.h"
#include "rx_replay.h"

#include <gtest/gtest.h>
#include <sodium.h>

#include <cstdio>
#include <map>
#include <string>
#include <utility>
#include <vector>

namespace
{
constexpr int K = 4;
constexpr int N = 8;
constexpr uint32_t kChannel = (7669206u << 8) + 0;

class CapturingTransmitter : public Transmitter
{
  public:
    CapturingTransmitter(const std::string& key) : Transmitter(K, N, key, 0, kChannel) {}
    std::vector<std::vector<uint8_t>> sent;
    void selectOutput(int) override {}
    void dumpStats(FILE*, uint64_t, uint32_t&, uint32_t&, uint32_t&) override {}

  protected:
    void injectPacket(const uint8_t* buf, size_t size) override { sent.emplace_back(buf, buf + size); }
};

// The radio packets of one session: the session key packet, and every data/parity fragment by (block, fragment),
// from data_nonce = (block << 8) | fragment in the clear header (wifibroadcast.hpp).
struct Stream
{
    std::vector<uint8_t> session;
    std::map<std::pair<uint64_t, int>, std::vector<uint8_t>> frag;
    std::string gsKey;
};

// closeAfter: payload indices after which the block is closed with FEC-only fillers (wfb_tx -Z, the air's
// close_fec_block: send_packet(NULL, 0, WFB_PACKET_FEC_ONLY) until the block is full).
Stream makeStream(int payloads, const std::vector<int>& closeAfter = {})
{
    EXPECT_EQ(sodium_init() >= 0, true);
    uint8_t txPub[crypto_box_PUBLICKEYBYTES], txSec[crypto_box_SECRETKEYBYTES];
    uint8_t rxPub[crypto_box_PUBLICKEYBYTES], rxSec[crypto_box_SECRETKEYBYTES];
    crypto_box_keypair(txPub, txSec);
    crypto_box_keypair(rxPub, rxSec);
    const std::string drone = "/tmp/rxdrain_drone.key", gs = "/tmp/rxdrain_gs.key";
    FILE* f = std::fopen(drone.c_str(), "wb");   // wfb-ng drone.key: tx secret + rx public
    std::fwrite(txSec, sizeof txSec, 1, f);
    std::fwrite(rxPub, sizeof rxPub, 1, f);
    std::fclose(f);
    f = std::fopen(gs.c_str(), "wb");            // wfb-ng gs.key: rx secret + tx public
    std::fwrite(rxSec, sizeof rxSec, 1, f);
    std::fwrite(txPub, sizeof txPub, 1, f);
    std::fclose(f);

    CapturingTransmitter tx(drone);
    tx.sendSessionKey();
    for (int i = 0; i < payloads; ++i)
    {
        const uint8_t p[2] = {'P', static_cast<uint8_t>(i)};
        tx.sendPacket(p, sizeof p, 0);
        for (int c : closeAfter)
            if (c == i)
                while (tx.sendPacket(nullptr, 0, WFB_PACKET_FEC_ONLY)) {
                }
    }
    Stream s;
    s.gsKey = gs;
    s.session = tx.sent.at(0);
    for (size_t i = 1; i < tx.sent.size(); ++i)
    {
        const std::vector<uint8_t>& pkt = tx.sent[i];
        uint64_t nonce = 0;
        for (int b = 1; b <= 8; ++b) nonce = (nonce << 8) | pkt[b];
        s.frag[{nonce >> 8, static_cast<int>(nonce & 0xFF)}] = pkt;
    }
    return s;
}

// Payload index i of each released packet ("P" + i).
std::vector<int> ids(const std::vector<std::vector<uint8_t>>& out)
{
    std::vector<int> v;
    for (const auto& p : out) v.push_back(p.size() == 2 && p[0] == 'P' ? p[1] : -1);
    return v;
}

struct Harness
{
    Stream s;
    RxReplay rx;
    std::vector<int> all;
    explicit Harness(Stream st = makeStream(3 * K)) : s(std::move(st)), rx(s.gsKey, kChannel) { rx.feed(s.session); }
    std::vector<int> feed(uint64_t block, int fragment)
    {
        const std::vector<int> got = ids(rx.feed(s.frag.at({block, fragment})));
        all.insert(all.end(), got.begin(), got.end());
        return got;
    }
};

using V = std::vector<int>;
}  // namespace

TEST(RxDrain, TheStreamHasTheExpectedFragments)
{
    Harness h;
    ASSERT_EQ(h.s.frag.size(), 3u * N);   // 3 blocks of 4 data + 4 parity
    for (int f = 0; f < K; ++f) EXPECT_EQ(h.feed(0, f), V{f});   // in order: each released on arrival
}

// R1 (FEC path): block 0 recovered through parity while block 1's first fragment is already there.
TEST(RxDrain, AfterAFecRecoveryTheNextBlocksWaitingFragmentIsReleasedInTheSameCall)
{
    Harness h;
    EXPECT_EQ(h.feed(0, 0), V{0});
    EXPECT_EQ(h.feed(0, 1), V{1});
    EXPECT_EQ(h.feed(0, 3), V{});        // fragment 2 lost: 3 waits behind the gap
    EXPECT_EQ(h.feed(1, 0), V{});        // block 1 is not the front yet
    EXPECT_EQ(h.feed(0, 4), (V{2, 3, 4})) << "block 1 fragment 0 (P4) must follow the recovered block 0";
    EXPECT_EQ(h.rx.fecRecovered(), 1u);
    EXPECT_EQ(h.feed(1, 1), V{5});
    EXPECT_EQ(h.all, (V{0, 1, 2, 3, 4, 5}));   // in order, no duplicates
}

// R2 (in-order path): block 0's last data fragment arrives after block 1's first two.
TEST(RxDrain, AfterALateFragmentCompletesTheFrontTheNextBlocksFragmentsAreReleasedInTheSameCall)
{
    Harness h;
    for (int f = 0; f < 3; ++f) EXPECT_EQ(h.feed(0, f), V{f});
    EXPECT_EQ(h.feed(1, 0), V{});
    EXPECT_EQ(h.feed(1, 1), V{});
    EXPECT_EQ(h.feed(0, 3), (V{3, 4, 5})) << "block 1 fragments 0-1 (P4, P5) must follow block 0";
    EXPECT_EQ(h.feed(1, 2), V{6});
    EXPECT_EQ(h.all, (V{0, 1, 2, 3, 4, 5, 6}));
}

TEST(RxDrain, AGapInTheNewFrontStopsTheReleaseAndFecRecoversItLater)
{
    Harness h;
    for (int f = 0; f < 3; ++f) h.feed(0, f);
    h.feed(1, 0);
    h.feed(1, 2);                          // block 1 fragment 1 lost
    EXPECT_EQ(h.feed(0, 3), (V{3, 4}));    // up to the gap only
    EXPECT_EQ(h.feed(1, 4), V{});          // 3 of k fragments
    EXPECT_EQ(h.feed(1, 5), (V{5, 6, 7})); // k: P5 and P7 (fragment 3 never sent) recovered, P6 in between
    EXPECT_EQ(h.all, (V{0, 1, 2, 3, 4, 5, 6, 7}));
}

// A block holding k fragments takes the FEC path and flushes the older ones (rx.cpp), so a block can wait behind
// the front with at most k - 1 fragments; the drain releases those and later fragments arrive on the normal path.
TEST(RxDrain, WaitingFragmentsAreReleasedAndTheBlockCarriesOnNormally)
{
    Harness h;
    for (int f = 0; f < 3; ++f) h.feed(0, f);
    for (int f = 0; f < K - 1; ++f) EXPECT_EQ(h.feed(1, f), V{});
    EXPECT_EQ(h.feed(0, 3), (V{3, 4, 5, 6}));   // block 0's end releases block 1's three waiting fragments
    EXPECT_EQ(h.feed(1, 3), V{7});              // block 1's last data fragment: released on arrival
    EXPECT_EQ(h.feed(1, 4), V{});               // its parity: already done, ignored
    EXPECT_EQ(h.feed(2, 0), V{8});              // block 2 is the front
    EXPECT_EQ(h.all, (V{0, 1, 2, 3, 4, 5, 6, 7, 8}));
}

// wfb_tx -Z closes a frame's block with FEC-only fillers. The Aggregator counts them towards k and uses them for
// FEC but never forwards them (send_packet: WFB_PACKET_FEC_ONLY), and their flag is inside the FEC-coded bytes, so a
// filler rebuilt by FEC is not forwarded either. The same code is in PixelPilot 0.21.0's wfb-ng 8f9b6a5
// (docs/xr/fec-block-probe.md §7). Frame 1 = P0, P1 + 2 fillers (block 0, k=4); frame 2 = P2..P5 (block 1).
namespace
{
Harness fillerHarness() { return Harness(makeStream(6, {1})); }
}  // namespace

TEST(RxFiller, FillersCloseTheBlockAndAreNeverForwarded)
{
    Harness h = fillerHarness();
    ASSERT_EQ(h.s.frag.size(), 2u * N);        // block 0 = 2 data + 2 fillers + 4 parity, block 1 = 4 + 4
    for (int f = 0; f < K; ++f) h.feed(0, f);
    for (int f = 0; f < K; ++f) h.feed(1, f);
    EXPECT_EQ(h.all, (V{0, 1, 2, 3, 4, 5}));   // no -1: nothing but the RTP-like payloads reaches the socket
    EXPECT_EQ(h.rx.lost(), 0u);
}

TEST(RxFiller, ABlockClosedByFillersRecoversALostDataPacket)
{
    Harness h = fillerHarness();
    EXPECT_EQ(h.feed(0, 0), V{0});
    EXPECT_EQ(h.feed(0, 2), V{});              // P1 lost; fillers wait behind the gap
    EXPECT_EQ(h.feed(0, 3), V{});
    EXPECT_EQ(h.feed(0, 4), V{1});             // parity: P1 rebuilt, the fillers are not forwarded
    EXPECT_EQ(h.rx.fecRecovered(), 1u);
    EXPECT_EQ(h.rx.lost(), 0u);
}

TEST(RxFiller, ARebuiltFillerIsNotForwardedEither)
{
    Harness h = fillerHarness();
    EXPECT_EQ(h.feed(0, 0), V{0});
    EXPECT_EQ(h.feed(0, 3), V{});              // P1 and filler 2 lost
    EXPECT_EQ(h.feed(0, 5), V{});
    EXPECT_EQ(h.feed(0, 6), V{1});             // k reached: P1 and the filler rebuilt, only P1 forwarded
    EXPECT_EQ(h.rx.fecRecovered(), 2u);
    EXPECT_EQ(h.feed(1, 0), V{2});
    EXPECT_EQ(h.rx.lost(), 0u);
}
