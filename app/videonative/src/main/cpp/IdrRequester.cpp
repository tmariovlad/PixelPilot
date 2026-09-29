#include "IdrRequester.h"

#include <arpa/inet.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <poll.h>
#include <sys/socket.h>
#include <unistd.h>

#include <cerrno>
#include <chrono>
#include <cstring>
#include <utility>

namespace {
int64_t nowMs()
{
    return std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now().time_since_epoch())
        .count();
}

// 1 = ready, 0 = timed out, -1 = error.
int waitFor(int fd, short events, int timeout_ms)
{
    pollfd p{fd, events, 0};
    const int n = poll(&p, 1, timeout_ms);
    if (n == 0) return 0;
    return n == 1 && (p.revents & events) != 0 ? 1 : -1;
}
}  // namespace

const char* IdrRequester::name(Result r)
{
    switch (r)
    {
        case Result::Ok: return "ok";
        case Result::Refused: return "refused";
        case Result::ConnectTimeout: return "connect_timeout";
        case Result::ReplyTimeout: return "reply_timeout";
        case Result::BadStatus: return "http_status";
        default: return "error";
    }
}

IdrRequester::IdrRequester(std::string host, uint16_t port, int min_interval_ms, int retry_window_ms)
    : m_host(std::move(host)),
      m_port(port),
      m_retry_window_ms(retry_window_ms),
      m_policy(min_interval_ms),
      m_thread(&IdrRequester::run, this)
{
}

IdrRequester::~IdrRequester()
{
    {
        std::lock_guard<std::mutex> lock(m_mutex);
        m_stop = true;
    }
    m_cv.notify_one();
    m_thread.join();
}

uint32_t IdrRequester::requestsFailed() const
{
    uint32_t n = 0;
    for (int i = 1; i < kResults; i++) n += m_counts[i];
    return n;
}

void IdrRequester::setMinIntervalMs(int ms)
{
    std::lock_guard<std::mutex> lock(m_mutex);
    m_policy.setIntervalMs(ms);
}

void IdrRequester::notifyLoss()
{
    if (!m_enabled) return;
    {
        std::lock_guard<std::mutex> lock(m_mutex);
        m_pending = true;
    }
    m_cv.notify_one();
}

void IdrRequester::run()
{
    std::unique_lock<std::mutex> lock(m_mutex);
    while (true)
    {
        m_cv.wait(lock, [this] { return m_stop || m_pending; });
        if (m_stop) return;
        // Wait out the interval; losses arriving meanwhile fold into this one request.
        const int64_t delay = m_policy.delayMs(nowMs());
        if (delay > 0 && m_cv.wait_for(lock, std::chrono::milliseconds(delay), [this] { return m_stop; })) return;
        m_pending         = false;
        const int64_t now = nowMs();
        if (!m_in_burst)
        {
            m_in_burst = true;
            m_burst_ms = now;
        }
        m_policy.sent(now);
        lock.unlock();
        const Result r = requestOnce();
        m_counts[static_cast<int>(r)]++;
        if (m_on_result) m_on_result(r);
        // Repeat while the key frame is still missing, within the retry window of this burst.
        const bool again = m_enabled && m_still_needed && nowMs() - m_burst_ms < m_retry_window_ms && m_still_needed();
        lock.lock();
        if (again)
            m_pending = true;
        else if (!m_pending)
            m_in_burst = false;
    }
}

IdrRequester::Result IdrRequester::requestOnce() const
{
    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port   = htons(m_port);
    if (inet_pton(AF_INET, m_host.c_str(), &addr.sin_addr) != 1) return Result::Error;
    const int fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0) return Result::Error;
    Result result = Result::Error;
    fcntl(fd, F_SETFL, fcntl(fd, F_GETFL, 0) | O_NONBLOCK);
    const int rc = connect(fd, reinterpret_cast<const sockaddr*>(&addr), sizeof(addr));
    int       err = rc == 0 ? 0 : errno;
    if (err == EINPROGRESS)
    {
        const int w = waitFor(fd, POLLOUT, kConnectTimeoutMs);
        socklen_t len = sizeof(err);
        if (w == 0)
            err = ETIMEDOUT;
        else if (getsockopt(fd, SOL_SOCKET, SO_ERROR, &err, &len) != 0)
            err = EIO;
    }
    if (err == ECONNREFUSED)
    {
        result = Result::Refused;
    }
    else if (err == ETIMEDOUT)
    {
        result = Result::ConnectTimeout;
    }
    else if (err == 0)
    {
        const std::string req = std::string("GET ") + kPath + " HTTP/1.0\r\nHost: " + m_host + "\r\n\r\n";
        if (send(fd, req.data(), req.size(), MSG_NOSIGNAL) == static_cast<ssize_t>(req.size()))
        {
            const int w = waitFor(fd, POLLIN, kReplyTimeoutMs);
            if (w == 0)
            {
                result = Result::ReplyTimeout;
            }
            else if (w == 1)
            {
                char          buf[64];
                const ssize_t n = recv(fd, buf, sizeof(buf) - 1, 0);
                if (n > 0)
                {
                    buf[n] = '\0';
                    const bool http = std::strncmp(buf, "HTTP/1.", 7) == 0;
                    result = http && std::strstr(buf, " 200") != nullptr ? Result::Ok : Result::BadStatus;
                }
            }
        }
    }
    close(fd);
    return result;
}
