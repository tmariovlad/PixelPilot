#pragma once

#include <exception>
#include <typeinfo>

// Runs a link body so that no exception can leave it.
//
// WfbngLink::run is called from a Java thread through JNI. An exception that escapes it ends in std::terminate
// and kills the app. devourer throws std::runtime_error and std::logic_error (e.g. jaguar1/HalModule.cpp,
// RadioManagementModule.cpp), and CreateRtlDevice used to sit outside the old runtime_error-only catch
// (audit X17, docs/xr/research/2026-09-27-xr-ux-audit.md).
//
// Returns body()'s result, or -1 after an exception. log(type, what) is called once per exception. The caller does
// its cleanup after this returns, on every path, in one place.
template <class Body, class Log>
int run_guarded(Body &&body, Log &&log) {
    try {
        return body();
    } catch (const std::exception &e) {
        log(typeid(e).name(), e.what());
    } catch (...) {
        log("unknown", "non-std exception");
    }
    return -1;
}
