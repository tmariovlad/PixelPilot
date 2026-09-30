// Differential fuzz: the same random drop/reorder patterns through one rx.cpp variant (stock or drain, chosen at build
// time by the include path). Prints, per case, the delivered payload ids with the call index each came out at, plus
// count_p_lost and count_p_fec_recovered. Two builds' outputs are compared by rx_fuzz_compare.py.
#include "TxFrame.h"
#include "rx_replay.h"

#include <sodium.h>

#include <cstdio>
#include <map>
#include <random>
#include <string>
#include <utility>
#include <vector>

namespace {
constexpr uint32_t kChannel = (7669206u << 8) + 0;

class CapTx : public Transmitter {
  public:
    CapTx(const std::string &key, int k, int n) : Transmitter(k, n, key, 0, kChannel) {}
    std::vector<std::vector<uint8_t>> sent;
    void selectOutput(int) override {}
    void dumpStats(FILE *, uint64_t, uint32_t &, uint32_t &, uint32_t &) override {}

  protected:
    void injectPacket(const uint8_t *b, size_t n) override { sent.emplace_back(b, b + n); }
};

void writeKeys(const char *drone, const char *gs) {
    uint8_t tp[crypto_box_PUBLICKEYBYTES], ts[crypto_box_SECRETKEYBYTES], rp[crypto_box_PUBLICKEYBYTES],
        rs[crypto_box_SECRETKEYBYTES];
    crypto_box_keypair(tp, ts);
    crypto_box_keypair(rp, rs);
    FILE *f = std::fopen(drone, "wb");
    std::fwrite(ts, sizeof ts, 1, f);
    std::fwrite(rp, sizeof rp, 1, f);
    std::fclose(f);
    f = std::fopen(gs, "wb");
    std::fwrite(rs, sizeof rs, 1, f);
    std::fwrite(tp, sizeof tp, 1, f);
    std::fclose(f);
}
}  // namespace

int main(int argc, char **argv) {
    const int cases = argc > 1 ? std::atoi(argv[1]) : 20000;
    if (sodium_init() < 0) return 1;
    const char *drone = "/tmp/rxfuzz_drone.key", *gs = "/tmp/rxfuzz_gs.key";
    writeKeys(drone, gs);
    const int geoms[][2] = {{4, 8}, {8, 10}, {8, 12}, {2, 4}};
    for (int c = 0; c < cases; ++c) {
        std::mt19937 rng(static_cast<uint32_t>(c));
        const int k = geoms[c % 4][0], n = geoms[c % 4][1];
        const int blocks = 3 + static_cast<int>(rng() % 6);
        const double drop = std::uniform_real_distribution<double>(0.0, 0.4)(rng);
        const double reorder = (c / 4) % 3 == 0 ? 0.0 : std::uniform_real_distribution<double>(0.0, 0.3)(rng);
        CapTx tx(drone, k, n);
        tx.sendSessionKey();
        for (int i = 0; i < blocks * k; ++i) {
            const uint8_t p[3] = {'P', static_cast<uint8_t>(i >> 8), static_cast<uint8_t>(i)};
            tx.sendPacket(p, sizeof p, 0);
        }
        // radio order: TX order, each packet dropped with p=drop, then local displacement (swap with a later one
        // up to 3 positions ahead) with p=reorder
        std::vector<size_t> order;
        for (size_t i = 1; i < tx.sent.size(); ++i)
            if (std::uniform_real_distribution<double>(0, 1)(rng) >= drop) order.push_back(i);
        for (size_t i = 0; i + 1 < order.size(); ++i)
            if (std::uniform_real_distribution<double>(0, 1)(rng) < reorder) {
                const size_t j = std::min(order.size() - 1, i + 1 + rng() % 3);
                std::swap(order[i], order[j]);
            }
        RxReplay rx(gs, kChannel);
        rx.feed(tx.sent[0]);
        std::printf("case %d k=%d n=%d blocks=%d |", c, k, n, blocks);
        int call = 0;
        for (size_t idx : order) {
            ++call;
            for (const auto &p : rx.feed(tx.sent[idx])) std::printf(" %d@%d", (p[1] << 8) | p[2], call);
        }
        std::printf(" | lost=%u rec=%u\n", rx.lost(), rx.fecRecovered());
    }
    return 0;
}
