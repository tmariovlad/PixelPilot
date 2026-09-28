#pragma once
#include <algorithm>
#include <android/log.h>
#include <chrono>
#include <cstdint>
#include <mutex>
#include <string>
#include <utility>
#include <vector>

// Adjust as needed
static const char *TAG = "SignalQualityCalculator";

class SignalQualityCalculator {
  public:
    // Average per receive chain (path A / path B) over the last second, in the device's raw units.
    struct ChainAverages {
        float ant1;
        float ant2;
    };

    struct SignalQuality {
        int lost_last_second;
        int recovered_last_second;
        int quality;
        float snr;
        std::string idr_code;
        ChainAverages rssi_chains;
        ChainAverages snr_chains;
    };

    SignalQualityCalculator() = default;
    ~SignalQualityCalculator() = default;

    void add_rssi(uint8_t ant1, uint8_t ant2);

    void add_snr(int8_t ant1, int8_t ant2);

    void add_fec_data(uint32_t p_all, uint32_t p_recovered, uint32_t p_lost);

    template <class T> ChainAverages get_chain_avgs(const T &array) {
        std::lock_guard<std::recursive_mutex> lock(m_mutex);

        // Remove old entries
        cleanup_old_rssi_data();

        float sum1 = 0.f;
        float sum2 = 0.f;
        int count = static_cast<int>(array.size());

        if (count > 0) {
            for (auto &entry : array) {
                sum1 += entry.ant1;
                sum2 += entry.ant2;
            }
            sum1 /= count;
            sum2 /= count;
        }
        return {sum1, sum2};
    }


    SignalQuality calculate_signal_quality();

    static SignalQualityCalculator &get_instance() {
        static SignalQualityCalculator instance;
        return instance;
    }

  private:
    std::pair<uint32_t, uint32_t> get_accumulated_fec_data();

    // Helper methods to remove old entries
    void cleanup_old_rssi_data();
    void cleanup_old_snr_data();
    void cleanup_old_fec_data();

    // We store a timestamp for each RSSI entry
    struct RssiEntry {
        std::chrono::steady_clock::time_point timestamp;
        uint8_t ant1;
        uint8_t ant2;
    };

    // We store a timestamp for each RSSI entry
    struct SnrEntry {
        std::chrono::steady_clock::time_point timestamp;
        int8_t ant1;
        int8_t ant2;
    };

    // We store a timestamp for each FEC entry
    struct FecEntry {
        std::chrono::steady_clock::time_point timestamp;
        uint32_t all;
        uint32_t recovered;
        uint32_t lost;
    };

    double map_range(double value, double inputMin, double inputMax, double outputMin, double outputMax) {
        return outputMin + ((value - inputMin) * (outputMax - outputMin) / (inputMax - inputMin));
    }

  private:
    const std::chrono::seconds kAveragingWindow{std::chrono::seconds(1)};
    mutable std::recursive_mutex m_mutex;

    std::vector<RssiEntry> m_rssis;

    std::vector<SnrEntry> m_snrs;

    std::vector<FecEntry> m_fec_data;

    std::string m_idr_code{"aaaa"};
};
