#include "StaFrames.h"

#include <gtest/gtest.h>

#include <map>
#include <string>
#include <vector>

using namespace sta;

namespace {
const Mac kSta{0x02, 0x42, 0x75, 0x05, 0xd6, 0x10};
const Mac kBss{0x98, 0x03, 0xcf, 0xcf, 0xa5, 0x2b};

// Walks the IEs after the fixed fields; returns {id -> body}.
std::map<int, std::vector<uint8_t>> ies(const std::vector<uint8_t>& f, size_t start) {
    std::map<int, std::vector<uint8_t>> m;
    for (size_t i = start; i + 2 <= f.size();) {
        size_t l = f[i + 1];
        EXPECT_LE(i + 2 + l, f.size());
        m[f[i]] = std::vector<uint8_t>(f.begin() + i + 2, f.begin() + i + 2 + l);
        i += 2 + l;
    }
    return m;
}
}  // namespace

TEST(StaFrames, AuthOpenLayout) {
    auto f = build_auth_open(kSta, kBss);
    ASSERT_EQ(f.size(), 30u);
    EXPECT_EQ(f[0], 0xb0);   // mgmt, subtype 11
    auto h = parse_header(f.data(), f.size());
    ASSERT_TRUE(h);
    EXPECT_EQ(h->a1, kBss);
    EXPECT_EQ(h->a2, kSta);
    EXPECT_EQ(h->a3, kBss);
    EXPECT_EQ(f[24], 0);   // Open System
    EXPECT_EQ(f[26], 1);   // transaction 1
}

TEST(StaFrames, AssocRequestCarriesRsnHtWmmAnd5GhzRates) {
    auto f = build_assoc_req(kSta, kBss, "OpenIPC", StaCaps{});
    EXPECT_EQ(f[0], 0x00);
    EXPECT_EQ(f[24] | (f[25] << 8), 0x0011);   // ESS + Privacy
    auto m = ies(f, 28);
    EXPECT_EQ(std::string(m[0].begin(), m[0].end()), "OpenIPC");
    EXPECT_EQ(m[1].front(), 0x8c);             // 6 Mbit/s basic, no CCK on 5 GHz
    EXPECT_EQ(m[48].size(), 20u);              // RSN
    EXPECT_EQ(m[48][11], 0x04);                // pairwise CCMP (group suite 2-5, count 6-7, pairwise 8-11)
    EXPECT_EQ(m[48][17], 0x02);                // AKM PSK
    ASSERT_EQ(m[45].size(), 26u);              // HT Capabilities
    EXPECT_EQ(m[45][0] & 0x02, 0);             // 20 MHz only
    EXPECT_EQ(m[45][2], 0);                    // no A-MPDU parameters promised
    ASSERT_EQ(m[221].size(), 7u);              // WMM information element
    EXPECT_EQ(m[221][3], 0x02);
}

TEST(StaFrames, AssocRequestWithoutOptionalElements) {
    StaCaps c;
    c.rsn = c.ht = c.wmm = false;
    c.channel = 6;
    auto f = build_assoc_req(kSta, kBss, "x", c);
    EXPECT_EQ(f[24] | (f[25] << 8), 0x0001);
    auto m = ies(f, 28);
    EXPECT_EQ(m.count(48) + m.count(45) + m.count(221), 0u);
    EXPECT_EQ(m[1].front(), 0x82);             // 1 Mbit/s basic on 2.4 GHz
}

TEST(StaFrames, ParseHeaderFlagsAndSequence) {
    std::vector<uint8_t> f(24, 0);
    f[0] = 0x88;                               // QoS data
    f[1] = 0x02 | 0x08 | 0x40;                 // from-DS, retry, protected
    f[22] = 0x50; f[23] = 0x12;                // seq 0x125, frag 0
    auto h = parse_header(f.data(), f.size());
    ASSERT_TRUE(h);
    EXPECT_EQ(h->type, FrameType::Data);
    EXPECT_EQ(h->subtype, 8);
    EXPECT_TRUE(h->from_ds);
    EXPECT_FALSE(h->to_ds);
    EXPECT_TRUE(h->retry);
    EXPECT_TRUE(h->protected_frame);
    EXPECT_EQ(h->seq, 0x125);
}

TEST(StaFrames, ParseHeaderRejectsControlAndShortFrames) {
    std::vector<uint8_t> ack(24, 0);
    ack[0] = 0xd4;                             // control, ACK
    EXPECT_FALSE(parse_header(ack.data(), ack.size()));
    EXPECT_FALSE(parse_header(ack.data(), 10));
}

TEST(StaFrames, BeaconSsidAndChannel) {
    std::vector<uint8_t> b(36, 0);
    b[0] = 0x80;
    for (int i = 0; i < 6; ++i) b[16 + i] = kBss[i];
    const char s[] = "OpenIPC";
    b.push_back(0); b.push_back(7); b.insert(b.end(), s, s + 7);
    b.push_back(3); b.push_back(1); b.push_back(157);
    auto i = parse_bss(b.data(), b.size());
    ASSERT_TRUE(i);
    EXPECT_EQ(i->ssid, "OpenIPC");
    EXPECT_EQ(i->channel, 157);
    b[37] = 30;                                // SSID length past the end -> reject
    EXPECT_FALSE(parse_bss(b.data(), b.size()));
}

TEST(StaFrames, ResponseStatus) {
    auto f = build_auth_open(kBss, kSta);      // same layout as the AP's reply
    f[28] = 17;                                // status 17: AP full (max_num_sta)
    EXPECT_EQ(response_status(f.data(), f.size()).value(), 17);
    std::vector<uint8_t> a(30, 0);
    a[0] = 0x10;                               // assoc response, status at 26
    a[26] = 0; a[27] = 0;
    EXPECT_EQ(response_status(a.data(), a.size()).value(), 0);
    EXPECT_FALSE(response_status(a.data(), 26));
}

TEST(StaFrames, PayloadLenStripsFcs) {
    EXPECT_EQ(payload_len(100), 96u);
    EXPECT_EQ(payload_len(3), 0u);
}
