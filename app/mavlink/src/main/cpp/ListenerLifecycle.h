#pragma once

#include <atomic>
#include <functional>
#include <mutex>
#include <thread>
#include <utility>

// Owns the one MAVLink listener thread, shared by the 2D and XR activities (audit X12,
// docs/xr/research/2026-09-27-xr-ux-audit.md).
//
// Before: nativeStart spawned a detached thread and nativeStop incremented a global flag that nothing ever
// reset, so after the first stop every later listener exited at once, and telemetry stayed dead for the rest of
// the process (2D included). And since the 2D activity's onStop runs after XR's onResume, a plain start/stop pair
// would let 2D kill XR's listener.
//
// Now: reference-counted. The first start() spawns the loop with a fresh stop flag; the last stop() sets the flag
// and joins, so the port is free before anyone binds it again. A loop that ended on its own (e.g. bind failed)
// is replaced by the next start(). Extra stop() calls are ignored.
class ListenerLifecycle {
  public:
    using Loop = std::function<void(const std::atomic<bool> &stop)>;

    explicit ListenerLifecycle(Loop loop) : loop_(std::move(loop)) {}
    ~ListenerLifecycle() { halt(); }
    ListenerLifecycle(const ListenerLifecycle &) = delete;
    ListenerLifecycle &operator=(const ListenerLifecycle &) = delete;

    void start() {
        std::lock_guard<std::mutex> lock(mutex_);
        ++users_;
        if (running_) return;
        joinLocked();          // a loop that ended on its own
        stop_ = false;
        running_ = true;
        thread_ = std::thread([this] {
            loop_(stop_);
            running_ = false;
        });
    }

    void stop() {
        std::lock_guard<std::mutex> lock(mutex_);
        if (users_ == 0) return;
        if (--users_ > 0) return;
        stop_ = true;
        joinLocked();
    }

    int users() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return users_;
    }

    bool running() const { return running_; }

  private:
    void halt() {
        std::lock_guard<std::mutex> lock(mutex_);
        users_ = 0;
        stop_ = true;
        joinLocked();
    }

    void joinLocked() {
        if (thread_.joinable()) thread_.join();
    }

    Loop loop_;
    mutable std::mutex mutex_;
    int users_ = 0;
    std::atomic<bool> stop_{false};
    std::atomic<bool> running_{false};
    std::thread thread_;
};
