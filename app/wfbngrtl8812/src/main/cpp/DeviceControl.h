#pragma once

#include <exception>
#include <map>
#include <memory>
#include <mutex>
#include <string>
#include <utility>

// The RTL devices (one per USB fd) and the one lock that sequences every control-plane call to them.
//
// Why a lock: devourer's contract (IRtlDevice.h:110-117) makes control calls "single-control-thread ... never
// concurrently with a channel set". On Jaguar1/2 "the USB-touching apply itself is the caller's to sequence".
// devourer ties nothing to a thread's identity (the only thread_local is log scratch, Event.h:233), so sequencing
// the calls is enough. WfbngLink reaches a device from several threads:
// - the link's run thread (one per adapter: WfbNgLink.java runs one nativeRun per UsbDevice on the same WfbngLink):
//   InitWrite, and the uplink start's SetTxPower;
// - the survey thread: SetMonitorChannel / FastRetune / GetRxEnergy, then the uplink start;
// - JNI threads: nativeSetTxPower, the adaptive-link restart's SetTxPower, nativeStop's StopRxLoop.
// Before this, two of them could call SetTxPower at once (OpenIPC master WfbngLink.cpp:246/536/568; pixelpilot-xr-25).
//
// Why the registry lives here (25's review F1/F2): the JNI thread used to look the device up in an unsynchronised
// std::map while run threads inserted and erased, and it fetched the pointer outside any lock. Now attach() and
// detach() share the lock with the calls. detach() runs Stop() and removes the device under that one lock, so a call
// sees either a live device or no device. It hands the device back, so the caller destroys it while the USB handle is
// still valid. A call for an fd without a device is a no-op: false, or a default value.
//
// Lock order: no WfbngLink or SurveyRunner lock is taken inside a device call. devourer takes its own internal locks
// (usb_lock; Jaguar3's coex/thermal tick), but no thread calls DeviceControl while holding one of them: the RX
// callbacks (packetProcessor, on_ring) never call it. So mu_ cannot deadlock.
// Not routed through it: StartRxLoop (the run thread's blocking loop on the device it just attached) and send_packet
// (the TX data path, stopped before detach; the survey keeps the uplink off while it hops).
// tests/DeviceControl_test.cpp covers four things: no two calls inside a device at once, no call after a device's
// Stop(), per-fd devices, and no raw device call in WfbngLink.cpp/.hpp.
template <class Dev> class DeviceControlT {
  public:
    using Ptr = std::shared_ptr<Dev>;

    // Registers d for fd. Returns null on success. It refuses an fd that already has a device: an fd number reused
    // while the old run still holds its device (25's hardening note) would otherwise free a device another run still
    // uses. The refused device is handed back, and the caller destroys it.
    [[nodiscard]] Ptr attach(int fd, Ptr d) {
        std::lock_guard<std::mutex> lock(mu_);
        auto it = devs_.find(fd);
        if (it != devs_.end() && it->second) return d;
        devs_[fd] = std::move(d);
        return nullptr;
    }

    // Removes fd's device and hands it back, but only when it is `expected` (the device this caller attached), so a
    // refused run's cleanup cannot take the other run's device. Returns null when that device is not registered.
    // With stop, Stop() (halt TRX DMA, power down) runs first under the same lock. An exception from it is reported in
    // *stop_error, and the device is still removed.
    Ptr detach(int fd, const Dev *expected, bool stop, std::string *stop_error) {
        std::lock_guard<std::mutex> lock(mu_);
        auto it = devs_.find(fd);
        if (it == devs_.end() || !expected || it->second.get() != expected) return nullptr;
        Ptr d = std::move(it->second);
        devs_.erase(it);
        if (stop && d) {
            try {
                d->Stop();
            } catch (const std::exception &e) {
                if (stop_error) *stop_error = e.what();
            }
        }
        return d;
    }

    template <class... A> bool initWrite(int fd, A &&...a) {
        return with(fd, [&](Dev *d) { d->InitWrite(std::forward<A>(a)...); });
    }
    template <class... A> bool setMonitorChannel(int fd, A &&...a) {
        return with(fd, [&](Dev *d) { d->SetMonitorChannel(std::forward<A>(a)...); });
    }
    template <class... A> bool fastRetune(int fd, A &&...a) {
        return with(fd, [&](Dev *d) { d->FastRetune(std::forward<A>(a)...); });
    }
    template <class... A> bool setTxPower(int fd, A &&...a) {
        return with(fd, [&](Dev *d) { d->SetTxPower(std::forward<A>(a)...); });
    }
    // Not a control-plane call (it only sets the RX loop's stop flag), routed here for the device's lifetime.
    bool stopRxLoop(int fd) {
        return with(fd, [](Dev *d) { d->StopRxLoop(); });
    }
    template <class... A> auto rxEnergy(int fd, A &&...a) {
        decltype(std::declval<Dev &>().GetRxEnergy(std::forward<A>(a)...)) r{};
        with(fd, [&](Dev *d) { r = d->GetRxEnergy(std::forward<A>(a)...); });
        return r;
    }
    auto selectedChannel(int fd) {
        decltype(std::declval<Dev &>().GetSelectedChannel()) r{};
        with(fd, [&](Dev *d) { r = d->GetSelectedChannel(); });
        return r;
    }

  private:
    template <class F> bool with(int fd, F &&f) {
        std::lock_guard<std::mutex> lock(mu_);
        auto it = devs_.find(fd);
        if (it == devs_.end() || !it->second) return false;
        f(it->second.get());
        return true;
    }

    std::mutex mu_;
    std::map<int, Ptr> devs_;
};
