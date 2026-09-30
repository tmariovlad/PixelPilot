#pragma once

#include <mutex>
#include <utility>

// Every control-plane call to the RTL goes through one DeviceControl. devourer's contract (IRtlDevice.h:110-117):
// control calls are "single-control-thread ... never concurrently with a channel set", and on Jaguar1/2 "the
// USB-touching apply itself is the caller's to sequence". devourer ties nothing to a thread's identity, so
// sequencing them is enough: one mutex.
//
// WfbngLink reaches the device from several threads:
// - the link's run thread: InitWrite, and the uplink start's SetTxPower;
// - the survey thread: SetMonitorChannel / FastRetune / GetRxEnergy, then the uplink start;
// - JNI threads: nativeSetTxPower, and the adaptive-link restart's SetTxPower.
// Before this, two of them could call SetTxPower at once (OpenIPC master WfbngLink.cpp:246/536/568; pixelpilot-xr-25).
//
// The lock is held for the one device call only, and it is always the innermost lock: nothing inside a call takes
// another lock, so it cannot deadlock against WfbngLink::thread_mutex or SurveyRunner's locks.
// Not routed through it:
// - StartRxLoop: it blocks for the link's life on the run thread;
// - StopRxLoop: the cross-thread stop signal the RX loop is built for;
// - send_packet: the TX data path. The survey keeps the uplink off while it hops.
// tests/DeviceControl_test.cpp: no two calls inside the device at once, and WfbngLink.cpp makes no raw
// control-plane call.
template <class Dev> class DeviceControlT {
  public:
    template <class... A> void initWrite(Dev *d, A &&...a) {
        std::lock_guard<std::mutex> lock(mu_);
        d->InitWrite(std::forward<A>(a)...);
    }
    template <class... A> void setMonitorChannel(Dev *d, A &&...a) {
        std::lock_guard<std::mutex> lock(mu_);
        d->SetMonitorChannel(std::forward<A>(a)...);
    }
    template <class... A> void fastRetune(Dev *d, A &&...a) {
        std::lock_guard<std::mutex> lock(mu_);
        d->FastRetune(std::forward<A>(a)...);
    }
    template <class... A> void setTxPower(Dev *d, A &&...a) {
        std::lock_guard<std::mutex> lock(mu_);
        d->SetTxPower(std::forward<A>(a)...);
    }
    template <class... A> auto rxEnergy(Dev *d, A &&...a) {
        std::lock_guard<std::mutex> lock(mu_);
        return d->GetRxEnergy(std::forward<A>(a)...);
    }
    auto selectedChannel(Dev *d) {
        std::lock_guard<std::mutex> lock(mu_);
        return d->GetSelectedChannel();
    }

  private:
    std::mutex mu_;
};
