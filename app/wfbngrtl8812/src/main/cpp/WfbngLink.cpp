#include "WfbngLink.hpp"

#include <android/asset_manager.h>
#include <android/asset_manager_jni.h>
#include <android/log.h>
#include <android/trace.h>
#include <jni.h>

#include "RxFrame.h"
#include "SignalQualityCalculator.h"
#include "LinkGuard.h"
#include "StatsWindow.h"
#include "TxFrame.h"
#include "WfbPktLostTap.h"
#include "WfbSessionTap.h"
#include "devourer/src/ChannelCenter.h"
#include "devourer/src/RxPacket.h"
#include "devourer/src/UsbDeviceLock.h"
#include "libusb.h"
#include "wfb-ng/src/wifibroadcast.hpp"

#include <arpa/inet.h>
#include <cstdlib>
#include <cxxabi.h>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <initializer_list>
#include <iomanip>
#include <iostream>
#include <list>
#include <map>
#include <mutex>
#include <netinet/in.h>
#include <random>
#include <span>
#include <sstream>
#include <string>
#include <sys/socket.h>
#include <thread>
#include <unistd.h>

#undef TAG
#define TAG "pixelpilot"

std::string generate_random_string(size_t length) {
    const std::string characters = "abcdefghijklmnopqrstuvwxyz";
    std::random_device rd;
    std::mt19937 gen(rd());
    std::uniform_int_distribution<> distrib(0, characters.size() - 1);

    std::string result;
    result.reserve(length);
    for (size_t i = 0; i < length; ++i) {
        result += characters[distrib(gen)];
    }
    return result;
}

namespace {
std::string filesDirOf(JNIEnv *env, jobject context) {
    jclass ctxClass = env->GetObjectClass(context);
    jmethodID getFilesDir = env->GetMethodID(ctxClass, "getFilesDir", "()Ljava/io/File;");
    jobject dir = env->CallObjectMethod(context, getFilesDir);
    jclass fileClass = env->GetObjectClass(dir);
    jmethodID getPath = env->GetMethodID(fileClass, "getAbsolutePath", "()Ljava/lang/String;");
    auto jpath = static_cast<jstring>(env->CallObjectMethod(dir, getPath));
    const char *chars = env->GetStringUTFChars(jpath, nullptr);
    std::string path(chars);
    env->ReleaseStringUTFChars(jpath, chars);
    return path;
}
}  // namespace

WfbngLink::WfbngLink(JNIEnv *env, jobject context)
        : current_fd(-1), adaptive_link_enabled(true), adaptive_tx_power(30),
          filesDir(filesDirOf(env, context)), keyPath(filesDir + "/gs.key") {
    initAgg();
    log = std::make_shared<Logger>(); // routes to logcat under the "devourer" tag
    wifi_driver = std::make_unique<WiFiDriver>(log);
}

void WfbngLink::initAgg() {
    std::string client_addr = "127.0.0.1";
    uint64_t epoch = 0;

    uint8_t video_radio_port = 0;
    uint32_t video_channel_id_f = (link_id << 8) + video_radio_port;
    video_channel_id_be = htobe32(video_channel_id_f);
    auto udsName = std::string("my_socket");

    video_aggregator = std::make_unique<VideoTapAggregator>(client_addr, 5600, keyPath, epoch, video_channel_id_f, 0,
                                                            video_rtp_probe);

    int mavlink_client_port = 14550;
    uint8_t mavlink_radio_port = 0x10;
    uint32_t mavlink_channel_id_f = (link_id << 8) + mavlink_radio_port;
    mavlink_channel_id_be = htobe32(mavlink_channel_id_f);

    mavlink_aggregator =
        std::make_unique<AggregatorUDPv4>(client_addr, mavlink_client_port, keyPath, epoch, mavlink_channel_id_f, 0);

    int udp_client_port = 8000;
    uint8_t udp_radio_port = wfb_rx_port;
    uint32_t udp_channel_id_f = (link_id << 8) + udp_radio_port;
    udp_channel_id_be = htobe32(udp_channel_id_f);

    udp_aggregator =
        std::make_unique<AggregatorUDPv4>(client_addr, udp_client_port, keyPath, epoch, udp_channel_id_f, 0);
}

int WfbngLink::run(JNIEnv *env, jobject context, jint wifiChannel, jint bw, jint fd) {
    int r;
    libusb_context *ctx = NULL;
    clear_stop_request(fd);
    txFrame = std::make_shared<TxFrame>();

    r = libusb_set_option(NULL, LIBUSB_OPTION_NO_DEVICE_DISCOVERY);
    r = libusb_init(&ctx);
    if (r < 0) {
        __android_log_print(ANDROID_LOG_ERROR, TAG, "Failed to init libusb.");
        return r;
    }

    // Open adapters
    struct libusb_device_handle *dev_handle;
    r = libusb_wrap_sys_device(ctx, (intptr_t)fd, &dev_handle);
    if (r < 0) {
        libusb_exit(ctx);
        return r;
    }

    // The adapter may still be held by the activity we are replacing (2D -> XR handoff): its link
    // thread releases the per-adapter lock only once its stop has completed. Wait for it (bounded)
    // instead of failing, and only then claim the interface. The lock is handed to
    // CreateRtlDevice, which then does not re-acquire it (devourer WiFiDriver.cpp).
    auto usb_lock = std::make_shared<devourer::UsbDeviceLock>();
    std::string lock_why;
    auto lock_res = usb_lock->try_acquire(libusb_get_device(dev_handle), &lock_why, filesDir);
    int lock_waits = 0;
    constexpr int kLockWaitSteps = 40;  // x 250 ms = 10 s
    while (lock_res == devourer::UsbDeviceLock::Result::Busy && lock_waits < kLockWaitSteps) {
        std::this_thread::sleep_for(std::chrono::milliseconds(250));
        ++lock_waits;
        lock_res = usb_lock->try_acquire(libusb_get_device(dev_handle), &lock_why, filesDir);
    }
    if (lock_res == devourer::UsbDeviceLock::Result::Busy) {
        __android_log_print(ANDROID_LOG_ERROR, TAG, "adapter still in use after %d ms (%s)",
                            lock_waits * 250, lock_why.c_str());
        libusb_close(dev_handle);
        libusb_exit(ctx);
        return -1;
    }
    if (lock_waits > 0) {
        __android_log_print(ANDROID_LOG_INFO, TAG, "adapter free after waiting %d ms", lock_waits * 250);
    }
    if (lock_res == devourer::UsbDeviceLock::Result::Error) {
        usb_lock.reset();  // lock infrastructure unavailable: let CreateRtlDevice degrade as before
    }

    if (libusb_kernel_driver_active(dev_handle, 0)) {
        r = libusb_detach_kernel_driver(dev_handle, 0);
        __android_log_print(ANDROID_LOG_DEBUG, TAG, "libusb_detach_kernel_driver: %d", r);
    }
    r = libusb_claim_interface(dev_handle, 0);
    __android_log_print(ANDROID_LOG_DEBUG, TAG, "Creating driver and device for fd=%d", fd);

    devourer::DeviceConfig cfg;
    // TX+RX on the one claimed handle. Jaguar3 (RTL8812EU/8822EU) must know
    // this before InitWrite so the bring-up keeps the RX filters open;
    // Jaguar1 (RTL8812AU) ignores it.
    cfg.rx.enable_with_tx = true;
    // The per-adapter advisory lock defaults to /tmp, which doesn't exist on
    // Android — use the app's files dir (same location as gs.key).
    cfg.usb.lock_dir = filesDir;
    // Keep the RX ring on plain heap buffers. The zerocopy dev-mem path
    // (libusb_dev_mem_alloc / USBDEVFS mmap) is unvalidated on Android vendor
    // kernels; if the mmap succeeds but the HCD's zerocopy path is broken,
    // the heap fallback never triggers. Heap is the behavior every working
    // Android build has shipped.
    cfg.usb.rx_zerocopy = false;
    // Link-audit diagnostics (T6, rx-diag-* prefs). Off by default.
    if (rx_diag_cfg.ring_ms > 0) {
        cfg.rx.ring_ms = rx_diag_cfg.ring_ms;
        cfg.rx.on_ring = [this](const devourer::RxRingStats &s) { rx_diag.on_ring(s); };
    }
    cfg.rx.keep_corrupted = rx_diag_cfg.keep_corrupted;
    if (rx_diag_cfg.rx_mode == 1 || rx_diag_cfg.rx_mode == 2) {
        cfg.rx.rx_mode = rx_diag_cfg.rx_mode == 1 ? devourer::RxMode::SpscFat : devourer::RxMode::ReorderPool;
        cfg.rx.pool_spare = 8;  // 16 buffers in flight or spare, as proposed in the audit (H2 test 4)
    }
    __android_log_print(ANDROID_LOG_INFO, TAG, "rx diag: ring_ms %d keep_corrupted %d rx_mode %d",
                        rx_diag_cfg.ring_ms, rx_diag_cfg.keep_corrupted ? 1 : 0, rx_diag_cfg.rx_mode);

    // Everything that can throw (devourer's CreateRtlDevice, bring-up, the RX loop) runs guarded, and every way out
    // - normal end, early abort, exception - goes through the one release_link() below (audit X17).
    uint8_t *video_channel_id_be8 = reinterpret_cast<uint8_t *>(&video_channel_id_be);
    uint8_t *udp_channel_id_be8 = reinterpret_cast<uint8_t *>(&udp_channel_id_be);
    uint8_t *mavlink_channel_id_be8 = reinterpret_cast<uint8_t *>(&mavlink_channel_id_be);

    const int result = run_guarded(
        [&]() -> int {
            rtl_devices[fd] = wifi_driver->CreateRtlDevice(dev_handle, ctx, usb_lock, cfg);
            // operator[] on purpose: a failed create leaves a null entry, which release_link() erases with find().
            // Do not "optimise" the check to .at().
            if (!rtl_devices[fd]) {
                __android_log_print(ANDROID_LOG_ERROR, TAG, "CreateRtlDevice error");
                return -1;
            }
            if (stop_requested(fd)) {
                __android_log_print(ANDROID_LOG_WARN, TAG, "stop requested for fd=%d before bring-up, aborting", fd);
                return -1;
            }
            const auto now_ms = [] {
                return std::chrono::duration_cast<std::chrono::milliseconds>(
                           std::chrono::steady_clock::now().time_since_epoch()).count();
            };
            {
                std::lock_guard<std::mutex> lock(agg_mutex);
                video_decrypt_probe.start(now_ms());
                video_fec_probe.setFcsVisible(rx_diag_cfg.keep_corrupted);   // bad-FCS frames reach us only then
            }
            auto packetProcessor =
                [this, video_channel_id_be8, mavlink_channel_id_be8, udp_channel_id_be8, now_ms](const Packet &packet) {
                    const int64_t t_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(
                                             std::chrono::steady_clock::now().time_since_epoch()).count();
                    if (rx_diag_cfg.keep_corrupted && packet.RxAtrib.crc_err) {
                        std::lock_guard<std::mutex> lock(agg_mutex);
                        video_fec_probe.onBadFcs(t_ns);
                    }
                    if (rx_diag_cfg.keep_corrupted && !rx_diag.on_frame(packet.RxAtrib.crc_err, packet.RxAtrib.icv_err)) {
                        return;  // a bad FCS/ICV: counted, never handed to wfb-ng (same as the chip dropping it)
                    }
                    RxFrame frame(packet.Data);
                    if (!frame.IsValidWfbFrame()) {
                        return;
                    }
                    int8_t rssi[4] = {(int8_t)packet.RxAtrib.rssi[0], (int8_t)packet.RxAtrib.rssi[1], 1, 1};
                    uint32_t freq = 0;
                    int8_t noise[4] = {1, 1, 1, 1};
                    uint8_t antenna[4] = {1, 1, 1, 1};

                    std::lock_guard<std::mutex> lock(agg_mutex);
                    video_fec_probe.onFrame(t_ns);   // every valid wfb frame: the gaps that make an outage
                    if (frame.MatchesChannelID(video_channel_id_be8)) {
                        SignalQualityCalculator::get_instance().add_rssi(packet.RxAtrib.rssi[0], packet.RxAtrib.rssi[1]);
                        SignalQualityCalculator::get_instance().add_snr(packet.RxAtrib.snr[0], packet.RxAtrib.snr[1]);
                        video_rx_rate.add(packet.RxAtrib.data_rate, packet.RxAtrib.bw, packet.RxAtrib.stbc,
                                          packet.RxAtrib.ldpc, packet.RxAtrib.sgi);

                        const uint8_t *payload = packet.Data.data() + sizeof(ieee80211_header);
                        const auto counters = [this] {
                            return DecErrProbe::Counters{video_aggregator->count_p_dec_err,
                                                         video_aggregator->count_p_data,
                                                         video_aggregator->count_p_session};
                        };
                        const DecErrProbe::Counters before = counters();
                        WfbSessionTap::clear();   // a SESSION logged during this call is the video channel's
                        WfbPktLostTap::clear();   // and so are the PKT_LOST slot counts
                        video_aggregator->beginCall(t_ns);
                        video_aggregator->process_packet(payload,
                                                         packet.Data.size() - sizeof(ieee80211_header) - 4,
                                                         0,
                                                         antenna,
                                                         rssi,
                                                         noise,
                                                         freq,
                                                         0,
                                                         0,
                                                         NULL);
                        video_aggregator->endCall();
                        const int64_t now = now_ms();
                        const DecErrProbe::Counters after = counters();
                        int fec_k = 0, fec_n = 0;
                        if (WfbSessionTap::consume(fec_k, fec_n)) {
                            video_fec_probe.onFec(fec_k, fec_n);
                            video_rtp_probe.onSession();
                        }
                        // slots lost before a payload that was not delivered (FEC-only padding): the next hole's
                        video_rtp_probe.onSlotsLost(WfbPktLostTap::take());
                        if (payload[0] == WFB_PACKET_DATA && after.data != before.data) {
                            // accepted (decrypted) data fragment: data_nonce = (block_idx << 8) + fragment_idx, BE
                            uint64_t nonce = 0;
                            for (int i = 1; i <= 8; ++i) nonce = (nonce << 8) | payload[i];
                            for (const std::string &line : video_fec_probe.onFragment(
                                     t_ns, nonce >> 8, static_cast<int>(nonce & 0xFF), packet.RxAtrib.rssi[0],
                                     packet.RxAtrib.rssi[1])) {
                                __android_log_print(ANDROID_LOG_INFO, "PPXR_FECBLK", "%s", line.c_str());
                            }
                        }
                        video_decrypt_probe.record(payload[0], before, after, now);
                        const std::string report = video_decrypt_probe.report(now);
                        if (!report.empty()) __android_log_print(ANDROID_LOG_WARN, TAG, "%s", report.c_str());
                    } else if (frame.MatchesChannelID(mavlink_channel_id_be8)) {
                        mavlink_aggregator->process_packet(packet.Data.data() + sizeof(ieee80211_header),
                                                           packet.Data.size() - sizeof(ieee80211_header) - 4,
                                                           0,
                                                           antenna,
                                                           rssi,
                                                           noise,
                                                           freq,
                                                           0,
                                                           0,
                                                           NULL);
                    } else if (frame.MatchesChannelID(udp_channel_id_be8)) {
                        udp_aggregator->process_packet(packet.Data.data() + sizeof(ieee80211_header),
                                                       packet.Data.size() - sizeof(ieee80211_header) - 4,
                                                       0,
                                                       antenna,
                                                       rssi,
                                                       noise,
                                                       freq,
                                                       0,
                                                       0,
                                                       NULL);
                    }
                };

            // Store the current fd for later TX power updates.
            current_fd = fd;

            IRtlDevice *current_device = rtl_devices.at(fd).get();

            // TX-capable bring-up with RX enabled (cfg.rx.enable_with_tx). On
            // Jaguar3 (RTL8812EU/8822EU) this also starts the coex runtime thread
            // that sustained TX needs.
            auto bandWidth = (bw == 20 ? CHANNEL_WIDTH_20 : CHANNEL_WIDTH_40);
            // At 40 MHz the primary must be explicit (it was DONT_CARE): it sets the RX primary and the sub-channel
            // of the 20 MHz uplink. In 5 GHz the channel's pair fixes it, e.g. 157 = HT40+ (primary lower, center 159)
            // (devourer ChannelCenter.h; docs/xr/research/2026-09-28-ht40-channel-center.md).
            current_device->InitWrite(SelectedChannel{
                .Channel = static_cast<uint8_t>(wifiChannel),
                .ChannelOffset = bandWidth == CHANNEL_WIDTH_40 ? devourer::ht40_offset(wifiChannel)
                                                               : devourer::kPrimeDontCare,
                .ChannelWidth = bandWidth,
            });

            if (!usb_tx_thread) {
                std::shared_ptr<TxArgs> args = std::make_shared<TxArgs>();
                args->udp_port = 8001;
                args->link_id = link_id;
                args->keypair = keyPath;
                args->stbc = stbc_enabled;
                args->ldpc = ldpc_enabled;
                const UplinkConfig up = uplink_config();
                args->mcs_index = up.mcs;
                args->vht_mode = false;
                args->short_gi = false;
                args->bandwidth = 20;
                args->k = static_cast<uint8_t>(up.fec_k);
                args->n = static_cast<uint8_t>(up.fec_n);
                args->radio_port = wfb_tx_port;

                __android_log_print(ANDROID_LOG_ERROR,
                                    TAG,
                                    "radio link ID %d, radio PORT %d, uplink FEC %d/%d MCS%d, %d reports/s",
                                    args->link_id,
                                    args->radio_port,
                                    up.fec_k,
                                    up.fec_n,
                                    up.mcs,
                                    up.rate_hz);

                // One TxFrame per TX thread: stop() is final for an instance (its loop exits and never restarts), so a
                // link that comes back (sleep/wake, replug) needs a fresh one. Reusing the old one made run() return at
                // once, leaving the uplink dead and its UDP socket open (2026-09-27, docs/xr/troubleshooting.md).
                txFrame = std::make_shared<TxFrame>();
                init_thread(usb_tx_thread, [&]() {
                    return std::make_unique<std::thread>([tx = txFrame, current_device, args] {
                        tx->run(current_device, args.get());
                        __android_log_print(ANDROID_LOG_DEBUG, TAG, "usb_transfer thread should terminate");
                    });
                });

                if (adaptive_link_enabled) {
                    stop_adaptive_link();
                    start_link_quality_thread(fd);
                }
            }

            // Blocking RX loop on this thread; devourer pumps the libusb events
            // itself. Returns once StopRxLoop() is called.
            if (stop_requested(fd)) {
                __android_log_print(
                    ANDROID_LOG_WARN, TAG, "stop requested for fd=%d during bring-up, not entering the rx loop", fd);
            } else {
                current_device->StartRxLoop(packetProcessor);
            }
            __android_log_print(ANDROID_LOG_DEBUG, TAG, "RX loop exited, releasing...");
            return 0;
        },
        [](const char *type, const char *what) {
            int status = 0;
            char *readable = abi::__cxa_demangle(type, nullptr, nullptr, &status);
            __android_log_print(ANDROID_LOG_ERROR, TAG, "link ended by an exception (%s): %s",
                                status == 0 && readable ? readable : type, what);
            std::free(readable);
        });
    release_link(fd, dev_handle, ctx);
    return result;
}

void WfbngLink::release_link(int fd, libusb_device_handle *dev_handle, libusb_context *ctx) {
    txFrame->stop();
    destroy_thread(usb_tx_thread);
    stop_adaptive_link();

    // Clean shutdown: halt TRX DMA and power the chip down before releasing the USB interface. find(), not at():
    // the device may never have been created (CreateRtlDevice threw or returned null).
    auto it = rtl_devices.find(fd);
    if (it != rtl_devices.end() && it->second) {
        try {
            it->second->Stop();
        } catch (const std::exception &e) {
            // Cleanup must not throw: it may run right after the link failed, and there is no caller left to catch.
            __android_log_print(ANDROID_LOG_ERROR, TAG, "device Stop() failed during release: %s", e.what());
        }
    }
    // Destroy the device while the handle is still valid: its destructor de-inits the chip and
    // releases the per-adapter lock. Kept in the map, it held the lock for the lifetime of this
    // WfbngLink, so the next activity (2D -> XR) found the adapter "in use" (2026-09-27).
    if (it != rtl_devices.end()) rtl_devices.erase(it);

    int r = libusb_release_interface(dev_handle, 0);
    __android_log_print(ANDROID_LOG_DEBUG, TAG, "libusb_release_interface: %d", r);
    libusb_exit(ctx);
}

void WfbngLink::stop(JNIEnv *env, jobject context, jint fd) {
    // Recorded first, and whether or not the device exists yet: run() may not have got as far
    // as creating it, and StartRxLoop() would clear the flag set below anyway.
    note_stop_requested(fd);
    if (rtl_devices.find(fd) == rtl_devices.end()) {
        // Happens when the adapter was already gone by the time the stop arrived, e.g. it
        // was unplugged or the hub re-enumerated it. Nothing left to stop.
        __android_log_print(ANDROID_LOG_WARN, TAG, "stop: no rtl device for fd=%d, already gone", fd);
        return;
    }
    auto dev = rtl_devices.at(fd).get();
    if (dev) {
        dev->StopRxLoop();
    } else {
        __android_log_print(ANDROID_LOG_ERROR, TAG, "rtl_devices.at(%d) is nullptr", fd);
    }
    stop_adaptive_link();
}

//--------------------------------------JAVA bindings--------------------------------------
inline jlong jptr(WfbngLink *wfbngLinkN) { return reinterpret_cast<intptr_t>(wfbngLinkN); }

inline WfbngLink *native(jlong ptr) { return reinterpret_cast<WfbngLink *>(ptr); }

inline std::list<int> toList(JNIEnv *env, jobject list) {
    // Get the class and method IDs for java.util.List and its methods
    jclass listClass = env->GetObjectClass(list);
    jmethodID sizeMethod = env->GetMethodID(listClass, "size", "()I");
    jmethodID getMethod = env->GetMethodID(listClass, "get", "(I)Ljava/lang/Object;");
    // Method ID to get int value from Integer object
    jclass integerClass = env->FindClass("java/lang/Integer");
    jmethodID intValueMethod = env->GetMethodID(integerClass, "intValue", "()I");

    // Get the size of the list
    jint size = env->CallIntMethod(list, sizeMethod);

    // Create a C++ list to store the elements
    std::list<int> res;

    // Iterate over the list and add elements to the C++ list
    for (int i = 0; i < size; ++i) {
        // Get the element at index i
        jobject element = env->CallObjectMethod(list, getMethod, i);
        // Convert the element to int
        jint value = env->CallIntMethod(element, intValueMethod);
        // Add the element to the C++ list
        res.push_back(value);
    }

    return res;
}
extern "C" JNIEXPORT jlong JNICALL Java_com_openipc_wfbngrtl8812_WfbNgLink_nativeInitialize(JNIEnv *env,
                                                                                            jclass clazz,
                                                                                            jobject context) {
    auto *p = new WfbngLink(env, context);
    return jptr(p);
}

extern "C" JNIEXPORT void JNICALL Java_com_openipc_wfbngrtl8812_WfbNgLink_nativeRun(
    JNIEnv *env, jclass clazz, jlong wfbngLinkN, jobject androidContext, jint wifiChannel, int bandWidth, jint fd) {
    native(wfbngLinkN)->run(env, androidContext, wifiChannel, bandWidth, fd);
}

extern "C" JNIEXPORT void JNICALL Java_com_openipc_wfbngrtl8812_WfbNgLink_nativeStartAdaptivelink(JNIEnv *env,
                                                                                                  jclass clazz,
                                                                                                  jlong wfbngLinkN) {
    if (native(wfbngLinkN)->video_aggregator == nullptr) {
        return;
    }
    auto aggregator = native(wfbngLinkN)->video_aggregator.get();
}

extern "C" JNIEXPORT jint JNICALL Java_com_openipc_pixelpilot_UsbSerialService_nativeGetSignalQuality(JNIEnv *env,
                                                                                                      jclass clazz) {
    return SignalQualityCalculator::get_instance().calculate_signal_quality().quality;
}

extern "C" JNIEXPORT void JNICALL Java_com_openipc_wfbngrtl8812_WfbNgLink_nativeStop(
    JNIEnv *env, jclass clazz, jlong wfbngLinkN, jobject androidContext, jint fd) {
    native(wfbngLinkN)->stop(env, androidContext, fd);
}

// One system-trace counter; no cost unless a trace is recording (API 29+).
static void trace_counter(const char *name, long long value) {
    if (__builtin_available(android 29, *)) {
        if (ATrace_isEnabled()) ATrace_setCounter(name, value);
    }
}

float map_range(float value, float inputMin, float inputMax, float outputMin, float outputMax) {
    return outputMin + ((value - inputMin) * (outputMax - outputMin) / (inputMax - inputMin));
}

extern "C" JNIEXPORT void JNICALL Java_com_openipc_wfbngrtl8812_WfbNgLink_nativeCallBack(JNIEnv *env,
                                                                                         jclass clazz,
                                                                                         jobject wfbStatChangedI,
                                                                                         jlong wfbngLinkN) {
    if (native(wfbngLinkN)->video_aggregator == nullptr) {
        return;
    }
    WfbngLink *link = native(wfbngLinkN);
    // Read and reset both aggregators' counters in one step under the RX thread's lock: a window without packets
    // then reports zeros instead of repeating the last one (StatsWindow.h).
    StatsWindow video, tunnel;
    {
        std::lock_guard<std::mutex> lock(link->agg_mutex);
        video = take_window(*link->video_aggregator);
        if (link->udp_aggregator) tunnel = take_window(*link->udp_aggregator);
    }
    // Link-audit RX diagnostics (T6): same window, as trace counters next to WfbStatsTrace's ppxr_wfb_*.
    if (link->rx_diag_cfg.enabled()) {
        RxDiag::emit(link->rx_diag.take(), trace_counter);
    }
    if (tunnel.all || tunnel.lost) {
        __android_log_print(ANDROID_LOG_INFO,
                            TAG,
                            "tunnel window: pkts %u lost %u fec_recovered %u dec_err %u",
                            tunnel.all,
                            tunnel.lost,
                            tunnel.fec_recovered,
                            tunnel.dec_err);
    }
    jclass jClassExtendsIWfbStatChangedI = env->GetObjectClass(wfbStatChangedI);
    jclass jcStats = env->FindClass("com/openipc/wfbngrtl8812/WfbNGStats");
    if (jcStats == nullptr) {
        return;
    }
    jmethodID jcStatsConstructor = env->GetMethodID(jcStats, "<init>", "(IIIIIIIIIIIII)V");
    if (jcStatsConstructor == nullptr) {
        return;
    }
    SignalQualityCalculator::get_instance().add_fec_data(video.all, video.fec_recovered, video.lost);

    auto quality = SignalQualityCalculator::get_instance().calculate_signal_quality();
    uint32_t avg_rssi_int = round(map_range(quality.quality, -1024.f, 1024.f, 0.f, 100.f));

    auto stats = env->NewObject(jcStats,
                                jcStatsConstructor,
                                (jint)video.all,
                                (jint)video.dec_err,
                                (jint)(video.all - video.dec_err),
                                (jint)video.fec_recovered,
                                (jint)video.lost,
                                (jint)video.bad,
                                (jint)video.override_,
                                (jint)video.outgoing,
                                (jint)avg_rssi_int,
                                (jint)lround(quality.rssi_chains.ant1),
                                (jint)lround(quality.rssi_chains.ant2),
                                (jint)lround(quality.snr_chains.ant1),
                                (jint)lround(quality.snr_chains.ant2));
    if (stats == nullptr) {
        return;
    }
    jmethodID onStatsChanged = env->GetMethodID(
        jClassExtendsIWfbStatChangedI, "onWfbNgStatsChanged", "(Lcom/openipc/wfbngrtl8812/WfbNGStats;)V");
    if (onStatsChanged == nullptr) {
        return;
    }
    env->CallVoidMethod(wfbStatChangedI, onStatsChanged, stats);
}

extern "C" JNIEXPORT void JNICALL Java_com_openipc_wfbngrtl8812_WfbNgLink_nativeRefreshKey(JNIEnv *env,
                                                                                           jclass clazz,
                                                                                           jlong wfbngLinkN) {
    native(wfbngLinkN)->initAgg();
}

// Modified start_link_quality_thread: use adaptive_link_enabled and adaptive_tx_power
void WfbngLink::start_link_quality_thread(int fd) {
    auto thread_func = [this, fd]() {
        std::this_thread::sleep_for(std::chrono::seconds(1));
        const char *ip = "10.5.0.10";
        int port = 9999;
        int sockfd;
        struct sockaddr_in server_addr;
        // Create UDP socket
        if ((sockfd = socket(AF_INET, SOCK_DGRAM, 0)) < 0) {
            __android_log_print(ANDROID_LOG_ERROR, TAG, "Socket creation failed");
            return;
        }
        int opt = 1;
        setsockopt(sockfd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));
        memset(&server_addr, 0, sizeof(server_addr));
        server_addr.sin_family = AF_INET;
        server_addr.sin_port = htons(port);
        if (inet_pton(AF_INET, ip, &server_addr.sin_addr) <= 0) {
            __android_log_print(ANDROID_LOG_ERROR, TAG, "Invalid IP address");
            close(sockfd);
            return;
        }

        UplinkSchedule schedule;
        while (!this->adaptive_link_should_stop) {
            auto quality = SignalQualityCalculator::get_instance().calculate_signal_quality();
            time_t currentEpoch = time(nullptr);
            const auto map_range =
                [](double value, double inputMin, double inputMax, double outputMin, double outputMax) {
                    return outputMin + ((value - inputMin) * (outputMax - outputMin) / (inputMax - inputMin));
                };
            // map to 1000..2000
            quality.quality = map_range(quality.quality, -1024, 1024, 1000, 2000);
            {
                uint32_t len;
                char message[100];

                /**
                     1741491090:1602:1602:1:0:-70:24:num_ants:pnlt:fec_change:code

                     <gs_time>:<link_score>:<link_score>:<fec>:<lost>:<rssi_dB>:<snr_dB>:<num_ants>:<noise_penalty>:<fec_change>:<idr_request_code>

                    gs_time: gs clock
                    link_score: 1000 - 2000 sent twice (already including any penalty)
                    link_score: 1000 - 2000 sent twice (already including any penalty)
                    fec: instantaneus fec_rec (only used by old fec_rec_pntly now disabled by default)
                    lost: instantaneus lost (not used)
                    rssi_dB:  best antenna rssi (for osd)
                    snr_dB: best antenna snr_dB (for osd)
                    num_ants: number of gs antennas (for osd)
                    noise_penalty: penalty deducted from score due to noise (for osd)
                    fec_change: int from 0 to 5 : how much to alter fec based on noise
                    optional idr_request_code:  4 char unique code to request 1 keyframe (no need to send special extra
                   packets)
                 */

                // Use the new public FEC threshold values
                if (quality.lost_last_second > fec_lost_to_5) {
                    fec.bump(5); // Bump to FEC 5
                } else if (quality.recovered_last_second > fec_recovered_to_4) {
                    fec.bump(4); // Bump to FEC 4
                } else if (quality.recovered_last_second > fec_recovered_to_3) {
                    fec.bump(3); // Bump to FEC 3
                } else if (quality.recovered_last_second > fec_recovered_to_2) {
                    fec.bump(2); // Bump to FEC 2
                } else if (quality.recovered_last_second > fec_recovered_to_1) {
                    fec.bump(1); // Bump to FEC 1
                }

                // Only when due (UplinkSchedule.h): every uplink frame costs video airtime.
                const int fec_change = fec.value();
                const int64_t now_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
                                           std::chrono::steady_clock::now().time_since_epoch())
                                           .count();
                const int interval_ms = uplink_config().interval_ms();
                if (!schedule.due(now_ms, interval_ms, quality.idr_code, fec_change)) {
                    std::this_thread::sleep_for(std::chrono::milliseconds(UplinkSchedule::kPollMs));
                    continue;
                }
                schedule.sent(now_ms, interval_ms, quality.idr_code, fec_change);

                snprintf(message + sizeof(len),
                         sizeof(message) - sizeof(len),
                         "%ld:%d:%d:%d:%d:%d:%f:0:-1:%d:%s\n",
                         static_cast<long>(currentEpoch),
                         quality.quality,
                         quality.quality,
                         quality.recovered_last_second,
                         quality.lost_last_second,
                         quality.quality,
                         quality.snr,
                         fec_change,
                         quality.idr_code.c_str());
                len = strlen(message + sizeof(len));
                len = htonl(len);
                memcpy(message, &len, sizeof(len));
                __android_log_print(ANDROID_LOG_ERROR, TAG, " message %s", message + 4);
                ssize_t sent = sendto(sockfd,
                                      message,
                                      strlen(message + sizeof(len)) + sizeof(len),
                                      0,
                                      (struct sockaddr *)&server_addr,
                                      sizeof(server_addr));
                if (sent < 0) {
                    __android_log_print(ANDROID_LOG_ERROR, TAG, "Failed to send message");
                    break;
                }
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(UplinkSchedule::kPollMs));
        }
        close(sockfd);
        this->adaptive_link_should_stop = false;
    };

    init_thread(link_quality_thread, [=]() { return std::make_unique<std::thread>(thread_func); });
    rtl_devices.at(fd)->SetTxPower(adaptive_tx_power);
}

extern "C" JNIEXPORT void JNICALL Java_com_openipc_wfbngrtl8812_WfbNgLink_nativeSetAdaptiveLinkEnabled(
    JNIEnv *env, jclass clazz, jlong wfbngLinkN, jboolean enabled) {
    WfbngLink *link = native(wfbngLinkN);
    bool wasEnabled = link->adaptive_link_enabled;
    link->adaptive_link_enabled = enabled;
    // If we are enabling adaptive mode (and it was previously disabled)
    if (enabled && !wasEnabled) {
        link->stop_adaptive_link();
        if (link->current_fd != -1) {
            // If a previous adaptive thread exists, join it first.
            // Restart the adaptive (link quality) thread.
            link->start_link_quality_thread(link->current_fd);
        }
    }
    // When disabling, wait for the thread to exit (if running).
    if (!enabled && wasEnabled) {
        link->stop_adaptive_link();
    }
}

extern "C" JNIEXPORT void JNICALL Java_com_openipc_wfbngrtl8812_WfbNgLink_nativeSetTxPower(JNIEnv *env,
                                                                                           jclass clazz,
                                                                                           jlong wfbngLinkN,
                                                                                           jint power) {
    WfbngLink *link = native(wfbngLinkN);
    if (link->adaptive_tx_power == power) return;

    link->adaptive_tx_power = power;
    if (link->current_fd != -1 && link->rtl_devices.find(link->current_fd) != link->rtl_devices.end()) {
        link->rtl_devices.at(link->current_fd)->SetTxPower(power);
    }
    // If adaptive mode is enabled and the adaptive thread is not running, restart it.
    if (link->adaptive_link_enabled) {
        link->stop_adaptive_link();
        if (link->current_fd != -1) {
            link->start_link_quality_thread(link->current_fd);
        }
    }
}

// The video packets' most frequent RX rate since the last call, as {rate code, bw, stbc, ldpc, sgi, packets at that
// rate, packets in the window} (RxRateHistogram.h); decoded into MCS/NSS by the app (stats.RxRate).
extern "C" JNIEXPORT jintArray JNICALL Java_com_openipc_wfbngrtl8812_WfbNgLink_nativeTakeRxRate(JNIEnv *env,
                                                                                                jclass clazz,
                                                                                                jlong wfbngLinkN) {
    const RxRateHistogram::Top t = native(wfbngLinkN)->video_rx_rate.take();
    const jint v[7] = {t.rateCode, t.bw, t.stbc, t.ldpc, t.sgi, static_cast<jint>(t.packets),
                       static_cast<jint>(t.total)};
    jintArray out = env->NewIntArray(7);
    env->SetIntArrayRegion(out, 0, 7, v);
    return out;
}

extern "C" JNIEXPORT void JNICALL Java_com_openipc_wfbngrtl8812_WfbNgLink_nativeSetUseFec(JNIEnv *env,
                                                                                          jclass clazz,
                                                                                          jlong wfbngLinkN,
                                                                                          jint use) {
    WfbngLink *link = native(wfbngLinkN);
    link->fec.setEnabled(use);
}

extern "C" JNIEXPORT void JNICALL Java_com_openipc_wfbngrtl8812_WfbNgLink_nativeSetUseLdpc(JNIEnv *env,
                                                                                           jclass clazz,
                                                                                           jlong wfbngLinkN,
                                                                                           jint use) {
    WfbngLink *link = native(wfbngLinkN);
    link->ldpc_enabled = (use != 0);
}

extern "C" JNIEXPORT void JNICALL Java_com_openipc_wfbngrtl8812_WfbNgLink_nativeSetUseStbc(JNIEnv *env,
                                                                                           jclass clazz,
                                                                                           jlong wfbngLinkN,
                                                                                           jint use) {
    WfbngLink *link = native(wfbngLinkN);
    link->stbc_enabled = (use != 0);
}

extern "C" JNIEXPORT void JNICALL Java_com_openipc_wfbngrtl8812_WfbNgLink_nativeSetFecThresholds(
    JNIEnv *env, jclass clazz, jlong nativeInstance, jint lostTo5, jint recTo4, jint recTo3, jint recTo2, jint recTo1) {
    WfbngLink *link = reinterpret_cast<WfbngLink *>(nativeInstance);
    if (!link) return;
    link->fec_lost_to_5 = lostTo5;
    link->fec_recovered_to_4 = recTo4;
    link->fec_recovered_to_3 = recTo3;
    link->fec_recovered_to_2 = recTo2;
    link->fec_recovered_to_1 = recTo1;
}
extern "C" JNIEXPORT void JNICALL Java_com_openipc_wfbngrtl8812_WfbNgLink_nativeSetRxDiag(
    JNIEnv *env, jclass clazz, jlong nativeInstance, jint ringMs, jboolean keepCorrupted, jint rxMode) {
    WfbngLink *link = reinterpret_cast<WfbngLink *>(nativeInstance);
    if (!link) return;
    link->rx_diag_cfg = WfbngLink::RxDiagConfig{ringMs, keepCorrupted == JNI_TRUE, rxMode};
}
extern "C" JNIEXPORT void JNICALL Java_com_openipc_wfbngrtl8812_WfbNgLink_nativeSetUplink(
    JNIEnv *env, jclass clazz, jlong nativeInstance, jint rateHz, jint fecK, jint fecN, jint mcs) {
    WfbngLink *link = reinterpret_cast<WfbngLink *>(nativeInstance);
    if (!link) return;
    link->set_uplink(UplinkConfig{rateHz, fecK, fecN, mcs});
}
