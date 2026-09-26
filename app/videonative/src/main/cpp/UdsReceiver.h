//
// UDSReceiver.h
// Unix‑Domain Datagram receiver running in its own thread
// Drop‑in companion to the existing UDPReceiver
//
// Created: 2025‑04‑18
//

#pragma once

#include <jni.h>  // JavaVM
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

#include <atomic>
#include <cstdint>
#include <functional>
#include <memory>
#include <string>
#include <thread>

class UDSReceiver
{
  public:
    using DATA_CALLBACK   = std::function<void(const uint8_t*, size_t)>;
    using SOURCE_CALLBACK = std::function<void(const char* /*peerPath*/)>;

    UDSReceiver(
        JavaVM*       javaVm,
        std::string   socketPath,   // e.g. "/data/local/tmp/my_socket"
        std::string   name,         // thread name
        int           CPUPriority,  // Android thread prio (ignored on desktop)
        DATA_CALLBACK onData,
        size_t        wantedRcvbufSize = 256 * 1024);

    // non‑copyable / movable
    UDSReceiver(const UDSReceiver&)            = delete;
    UDSReceiver& operator=(const UDSReceiver&) = delete;
    UDSReceiver(UDSReceiver&&)                 = delete;
    UDSReceiver& operator=(UDSReceiver&&)      = delete;

    ~UDSReceiver() { stopReceiving(); }

    // control
    void startReceiving();
    void stopReceiving();

    // Kernel thread id of the receive/parse/feed thread (0 if not running).
    int threadId() const { return mTid.load(); }

    // callbacks
    void registerOnSourceFound(SOURCE_CALLBACK cb) { onSource = std::move(cb); }

    // stats / info
    [[nodiscard]] long        getNReceivedBytes() const { return nReceivedBytes; }
    [[nodiscard]] std::string getSourcePath() const { return senderPath; }

  private:
    void receiveLoop();

    // ctor constants
    const std::string   mSocketPath;
    const std::string   mName;
    const size_t        WANTED_RCVBUF_SIZE;
    const int           mCPUPriority;
    const DATA_CALLBACK onData;
    JavaVM* const       javaVm;

    // runtime
    int                          mSocket = -1;
    std::unique_ptr<std::thread> mThread;
    std::atomic<int>             mTid{0};  // kernel tid of the receive thread, 0 until it runs
    std::atomic<bool>            receiving{false};
    std::atomic<long>            nReceivedBytes{0};
    std::string                  senderPath;
    SOURCE_CALLBACK              onSource;
};
