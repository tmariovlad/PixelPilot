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

bool waitFor(int fd, short events, int timeout_ms)
{
    pollfd p{fd, events, 0};
    return poll(&p, 1, timeout_ms) == 1 && (p.revents & events) != 0;
}
}  // namespace

IdrRequester::IdrRequester(std::string host, uint16_t port, int min_interval_ms)
    : m_host(std::move(host)), m_port(port), m_policy(min_interval_ms), m_thread(&IdrRequester::run, this)
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
        m_pending = false;
        m_policy.sent(nowMs());
        lock.unlock();
        const bool ok = requestOnce();
        (ok ? m_ok : m_failed)++;
        if (m_on_result) m_on_result(ok);
        lock.lock();
    }
}

bool IdrRequester::requestOnce() const
{
    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port   = htons(m_port);
    if (inet_pton(AF_INET, m_host.c_str(), &addr.sin_addr) != 1) return false;
    const int fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0) return false;
    bool ok = false;
    fcntl(fd, F_SETFL, fcntl(fd, F_GETFL, 0) | O_NONBLOCK);
    const int rc = connect(fd, reinterpret_cast<const sockaddr*>(&addr), sizeof(addr));
    int       err = 0;
    socklen_t len = sizeof(err);
    if ((rc == 0 || (errno == EINPROGRESS && waitFor(fd, POLLOUT, kTimeoutMs))) &&
        getsockopt(fd, SOL_SOCKET, SO_ERROR, &err, &len) == 0 && err == 0)
    {
        const std::string req = std::string("GET ") + kPath + " HTTP/1.0\r\nHost: " + m_host + "\r\n\r\n";
        char              buf[64];
        if (send(fd, req.data(), req.size(), MSG_NOSIGNAL) == static_cast<ssize_t>(req.size()) &&
            waitFor(fd, POLLIN, kTimeoutMs))
        {
            const ssize_t n = recv(fd, buf, sizeof(buf) - 1, 0);
            if (n > 0)
            {
                buf[n] = '\0';
                ok     = std::strncmp(buf, "HTTP/1.", 7) == 0 && std::strstr(buf, " 200") != nullptr;
            }
        }
    }
    close(fd);
    return ok;
}
