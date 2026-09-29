#pragma once

#include <algorithm>
#include <cstdint>
#include <deque>
#include <map>
#include <string>
#include <vector>

// One PPXR_FECBLK line per video FEC block that wfb-ng could not recover, to find the cause of the short outages
// that take out whole blocks (loss-bursts-2026-09-29, docs/xr/fec-block-probe.md): which fragments arrived, their RSSI,
// the block's time span, the longest gap between received frames while the block was pending (the outage), and the
// bad-FCS frames around it (only when devourer's keep_corrupted is on).
//
// It mirrors wfb-ng's Aggregator (src/rx.cpp, process_packet): a block is recovered once it holds k distinct
// fragments; at that moment every older block still short of k is flushed and its missing data counted as lost
// ("flush"); a block falling out of the RX_RING_SIZE-block ring is dropped too ("ring"). Fed on the RX thread with the
// fragments the video aggregator accepted (decrypted). Times are CLOCK_MONOTONIC ns; RSSI is devourer's raw value
// (dBm = raw - 110, converted by the parser). At most kMaxLinesPerSecond lines per second; the next second's first
// line says how many were suppressed. Not thread-safe (RX thread only).
class FecBlockProbe {
  public:
    static constexpr uint64_t kRingBlocks = 40;          // wfb-ng RX_RING_SIZE (src/rx.hpp:79)
    static constexpr int64_t kFcsBeforeNs = 10'000'000;  // bad-FCS frames counted from 10 ms before the block
    static constexpr int kMaxLinesPerSecond = 10;
    static constexpr uint64_t kRestartBlocks = 4 * kRingBlocks;  // block index this far back = a new session

    void onFec(int k, int n) {
        k_ = k;
        n_ = n;
        pending_.clear();
        haveDone_ = false;
    }

    void setFcsVisible(bool visible) { fcsVisible_ = visible; }

    // Every valid wfb frame on the radio (any channel), for the inter-arrival gaps.
    void onFrame(int64_t tNs) {
        const int64_t gap = lastFrameNs_ > 0 ? tNs - lastFrameNs_ : 0;
        lastFrameNs_ = tNs;
        for (auto &kv : pending_) kv.second.maxGapNs = std::max(kv.second.maxGapNs, gap);
    }

    void onBadFcs(int64_t tNs) {
        badFcs_.push_back(tNs);
        while (!badFcs_.empty() && badFcs_.front() < tNs - 2'000'000'000LL) badFcs_.pop_front();
    }

    // A video fragment the aggregator accepted. Returns the lines for the blocks this fragment made wfb-ng give up on.
    std::vector<std::string> onFragment(int64_t tNs, uint64_t block, int fragment, int rssiA, int rssiB) {
        std::vector<std::string> out;
        if (k_ < 1 || fragment < 0 || fragment >= n_) return out;
        if (haveDone_ && block + kRestartBlocks < done_) {   // the block numbers started again: a new session
            pending_.clear();
            haveDone_ = false;
        }
        if (haveDone_ && block <= done_) return out;         // already recovered or flushed
        Block &b = pending_[block];
        if (b.map.empty()) {
            b.map.assign(static_cast<size_t>(n_), false);
            b.firstNs = tNs;
        }
        if (b.map[static_cast<size_t>(fragment)]) return out;   // a duplicate
        b.map[static_cast<size_t>(fragment)] = true;
        b.frags.push_back({fragment, tNs, rssiA, rssiB});
        ++b.count;

        while (!pending_.empty() && pending_.begin()->first + kRingBlocks <= block) {
            fail(pending_.begin()->first, pending_.begin()->second, tNs, "ring", 0, out);
            markDone(pending_.begin()->first);
            pending_.erase(pending_.begin());
        }
        if (b.count >= k_) {
            while (!pending_.empty() && pending_.begin()->first < block) {
                fail(pending_.begin()->first, pending_.begin()->second, tNs, "flush", block, out);
                pending_.erase(pending_.begin());
            }
            pending_.erase(block);
            markDone(block);
        }
        return out;
    }

  private:
    struct Frag {
        int idx;
        int64_t tNs;
        int rssiA, rssiB;
    };
    struct Block {
        std::vector<bool> map;
        std::vector<Frag> frags;
        int count = 0;
        int64_t firstNs = 0;
        int64_t maxGapNs = 0;
    };

    void markDone(uint64_t block) {
        if (!haveDone_ || block > done_) done_ = block;
        haveDone_ = true;
    }

    int fcsAround(const Block &b, int64_t flushNs) const {
        int n = 0;
        for (int64_t t : badFcs_)
            if (t >= b.firstNs - kFcsBeforeNs && t <= flushNs) ++n;
        return n;
    }

    void fail(uint64_t block, const Block &b, int64_t nowNs, const char *reason, uint64_t next,
              std::vector<std::string> &out) {
        const int64_t second = nowNs / 1'000'000'000LL;
        if (second != second_) {
            second_ = second;
            linesThisSecond_ = 0;
            carrySuppressed_ += suppressed_;
            suppressed_ = 0;
        }
        if (linesThisSecond_ >= kMaxLinesPerSecond) {
            ++suppressed_;
            return;
        }
        ++linesThisSecond_;
        std::string got;
        for (bool f : b.map) got += f ? '1' : '0';
        int64_t lastNs = b.firstNs;
        std::string frags;
        for (const Frag &f : b.frags) {
            lastNs = std::max(lastNs, f.tNs);
            if (!frags.empty()) frags += ',';
            frags += std::to_string(f.idx) + ':' + std::to_string((f.tNs - b.firstNs) / 1000) + ':' +
                     std::to_string(f.rssiA) + ':' + std::to_string(f.rssiB);
        }
        std::string line = "t_mono_ms=" + std::to_string(nowNs / 1'000'000) + " blk=" + std::to_string(block) +
                           " k=" + std::to_string(k_) + " n=" + std::to_string(n_) + " got=" + got +
                           " span_us=" + std::to_string((lastNs - b.firstNs) / 1000) +
                           " gap_max_us=" + std::to_string(b.maxGapNs / 1000) + " frags=" + frags +
                           " fcs=" + (fcsVisible_ ? std::to_string(fcsAround(b, nowNs)) : std::string("-")) +
                           " reason=" + reason;
        if (next != 0 || std::string(reason) == "flush") line += " next=" + std::to_string(next);
        if (carrySuppressed_ > 0) {
            line += " suppressed=" + std::to_string(carrySuppressed_);
            carrySuppressed_ = 0;
        }
        out.push_back(line);
    }

    int k_ = 0, n_ = 0;
    bool fcsVisible_ = false;
    std::map<uint64_t, Block> pending_;
    bool haveDone_ = false;
    uint64_t done_ = 0;
    int64_t lastFrameNs_ = 0;
    std::deque<int64_t> badFcs_;
    int64_t second_ = -1;
    int linesThisSecond_ = 0;
    int suppressed_ = 0;
    int carrySuppressed_ = 0;
};
