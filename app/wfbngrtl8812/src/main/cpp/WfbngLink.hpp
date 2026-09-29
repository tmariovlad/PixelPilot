#ifndef FPV_VR_WFBNG_LINK_H
#define FPV_VR_WFBNG_LINK_H

#include "DecErrProbe.h"
#include "RxDiag.h"
#include "FecBlockProbe.h"
#include "RxRateHistogram.h"
#include "FecChangeController.h"
#include "SignalQualityCalculator.h"
#include "TxFrame.h"
#include "UplinkSchedule.h"

extern "C" {
#include "wfb-ng/src/zfex.h"
}

#include "devourer/src/IRtlDevice.h"
#include "devourer/src/WiFiDriver.h"
#include "wfb-ng/src/rx.hpp"
#include "VideoTapAggregator.h"
#include <cstdint>
#include <functional>
#include <jni.h>
#include <list>
#include <map>
#include <mutex>
#include <set>
#include <thread>
#include <vector> // Added for std::vector

const uint8_t wfb_tx_port = 160;
const uint8_t wfb_rx_port = 32;

struct libusb_context;        // libusb.h is included by WfbngLink.cpp
struct libusb_device_handle;

class WfbngLink {
  public:
    // FEC switching thresholds (for menu)
    int fec_lost_to_5 = 2;
    int fec_recovered_to_4 = 30;
    int fec_recovered_to_3 = 24;
    int fec_recovered_to_2 = 14;
    int fec_recovered_to_1 = 8;
    WfbngLink(JNIEnv *env, jobject context);

    int run(JNIEnv *env, jobject androidContext, jint wifiChannel, jint bw, jint fd);
    // The single cleanup of run(): TX, adaptive link, device Stop()/destroy, USB interface, libusb context.
    void release_link(int fd, libusb_device_handle *dev_handle, libusb_context *ctx);

    void initAgg();

    void stop(JNIEnv *env, jobject androidContext, jint fd);

    std::mutex agg_mutex;
    std::unique_ptr<VideoTapAggregator> video_aggregator;
    DecErrProbe video_decrypt_probe;   // guarded by agg_mutex, like the aggregator
    RxRateHistogram video_rx_rate;     // RX rate of the video packets per stats window (Stats page)
    FecBlockProbe video_fec_probe;     // PPXR_FECBLK per unrecoverable video FEC block; guarded by agg_mutex
    RtpHoleProbe video_rtp_probe;      // PPXR_RTPHOLE per hole in the delivered RTP sequence; guarded by agg_mutex
    std::unique_ptr<AggregatorUDPv4> mavlink_aggregator;
    std::unique_ptr<AggregatorUDPv4> udp_aggregator;

    // Link-audit RX diagnostics (T6), set from the app's rx-diag-* prefs before run(); all off by default, so the
    // default RX path is unchanged. ring_ms > 0: devourer ring telemetry; keep_corrupted: FCS/ICV-failed frames
    // reach the host and are counted, then dropped; rx_mode 0 = async (default), 1 = spsc-fat, 2 = reorder-pool.
    struct RxDiagConfig {
        int ring_ms = 0;
        bool keep_corrupted = false;
        int rx_mode = 0;
        bool enabled() const { return ring_ms > 0 || keep_corrupted; }
    };
    RxDiagConfig rx_diag_cfg;
    RxDiag rx_diag;

    void start_link_quality_thread(int fd);

    // adaptive link
    // TODO: move this to private section
    int current_fd;
    bool adaptive_link_enabled;
    bool adaptive_link_should_stop{false};
    int adaptive_tx_power;

    // Runtime configurable PHY parameters
    bool ldpc_enabled{true};
    bool stbc_enabled{true};

    // Uplink airtime (UplinkSchedule.h). The report rate applies at once; FEC and MCS at the next link start.
    void set_uplink(const UplinkConfig &c) {
        std::lock_guard<std::mutex> lock(uplink_mutex);
        uplink = c.sanitized();
    }
    UplinkConfig uplink_config() {
        std::lock_guard<std::mutex> lock(uplink_mutex);
        return uplink;
    }

    std::map<int, std::shared_ptr<IRtlDevice>> rtl_devices;

    // Set by stop() and read by run(). A StopRxLoop() only takes effect once the RX loop is
    // running: RtlJaguarDevice::StartRxLoop() clears should_stop on entry, so a stop that
    // lands anywhere before that - including the whole chip bring-up in InitWrite(), which
    // is the longest part of run() - is thrown away, and run() then blocks in a loop nobody
    // asked for. Recorded here instead, so run() can see it at the points where the flag
    // itself cannot be trusted.
    std::mutex    stop_requested_mutex;
    std::set<int> stop_requested_fds;

    void note_stop_requested(int fd) {
        std::lock_guard<std::mutex> lock(stop_requested_mutex);
        stop_requested_fds.insert(fd);
    }

    // Cleared at the start of run(): fd numbers are reused, so a request left over from a
    // previous session on the same number must not abort the new one.
    void clear_stop_request(int fd) {
        std::lock_guard<std::mutex> lock(stop_requested_mutex);
        stop_requested_fds.erase(fd);
    }

    bool stop_requested(int fd) {
        std::lock_guard<std::mutex> lock(stop_requested_mutex);
        return stop_requested_fds.count(fd) > 0;
    }
    std::unique_ptr<std::thread> link_quality_thread{nullptr};
    FecChangeController fec;

    void init_thread(std::unique_ptr<std::thread> &thread,
                     const std::function<std::unique_ptr<std::thread>()> &init_func) {
        std::unique_lock<std::recursive_mutex> lock(thread_mutex);
        destroy_thread(thread);
        thread = init_func();
    }

    void destroy_thread(std::unique_ptr<std::thread> &thread) {
        std::unique_lock<std::recursive_mutex> lock(thread_mutex);
        if (thread && thread->joinable()) {
            thread->join();
            thread = nullptr;
        }
    }

    void stop_adaptive_link() {
        std::unique_lock<std::recursive_mutex> lock(thread_mutex);

        if (!link_quality_thread) return;
        this->adaptive_link_should_stop = true;
        destroy_thread(link_quality_thread);
    }

  private:
    void stopDevice() {
        if (rtl_devices.find(current_fd) == rtl_devices.end()) return;
        auto dev = rtl_devices.at(current_fd).get();
        if (dev) {
            dev->StopRxLoop();
        }
    }

    // The app's files dir (Context.getFilesDir()), resolved in the constructor so the paths follow the
    // real package name (e.g. a ".xr" debug build) instead of a hard-coded one.
    std::string filesDir;
    std::string keyPath;
    std::recursive_mutex thread_mutex;
    std::mutex uplink_mutex;
    UplinkConfig uplink;
    std::unique_ptr<WiFiDriver> wifi_driver;
    std::shared_ptr<TxFrame> txFrame;
    uint32_t video_channel_id_be;
    uint32_t mavlink_channel_id_be;
    uint32_t udp_channel_id_be;

    Logger_t log;
    std::unique_ptr<std::thread> usb_tx_thread{nullptr};
    uint32_t link_id{7669206};
    SignalQualityCalculator rssi_calculator;
};

#endif // FPV_VR_WFBNG_LINK_H
