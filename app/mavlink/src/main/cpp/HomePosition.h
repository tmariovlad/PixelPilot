#pragma once

// The home position for "distance from home".
//
// Before: every armed HEARTBEAT copied the current position into home, so home followed the aircraft and the
// distance stayed 0 for the whole flight (seen on the Quest, 2026-09-27, with synthetic telemetry). Now home is
// taken once per arming, at the first moment the aircraft is armed with a GPS fix, and forgotten on disarm so the
// next arming sets a new one.
struct HomePosition {
    double lat = 0;   // 1e-7 deg, as MAVLink sends it
    double lon = 0;
    bool set = false;

    // Call on every HEARTBEAT (and whenever the fix changes) with the current state.
    void update(bool armed, int gps_fix_type, double cur_lat, double cur_lon) {
        if (!armed) {
            set = false;
            return;
        }
        if (!set && gps_fix_type != 0) {
            lat = cur_lat;
            lon = cur_lon;
            set = true;
        }
    }
};
