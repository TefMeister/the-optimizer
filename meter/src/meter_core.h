// meter_core.h -- the counting part of the Tune-o-matiC frame meter, kept free of OpenXR and Windows so the host test
// (test/meter_test.cpp) can drive it with made-up clocks. The layer (meter_layer.cpp) feeds it three moments per
// frame: the game asks to wait for the next frame, the wait returns (with the headset's frame period), the game hands
// the frame in. From those it makes one row per frame and a small rolling summary for the live guard.
//
// One row per frame:
//   t_ms         when the wait returned, from the first frame of the session
//   interval_ms  wait return to wait return: the real time between two frames the headset got
//   wait_ms      how long the game sat in the wait (long = the game is ahead and waiting for the headset)
//   work_ms      wait return to frame handed in: the game's own work on the frame (CPU side)
//   period_ms    the headset's frame time (13.89 ms at 72 Hz), as the runtime says it
//   missed       1 when interval_ms is over MISSED_FACTOR periods: the headset showed an old frame
#pragma once
#include <cstdint>
#include <cstdio>
#include <deque>
#include <mutex>
#include <string>
#include <vector>

namespace tm_meter {

constexpr double MISSED_FACTOR = 1.5;     // an interval over 1.5 periods means at least one frame was not ready
constexpr double LIVE_WINDOW_MS = 2000;   // the rolling summary covers the last two seconds
constexpr double NS_PER_MS = 1e6;

struct Row {
    double t_ms, interval_ms, wait_ms, work_ms, period_ms;
    int missed;
};

struct Live {
    double fps = 0, period_ms = 0, worst_ms = 0;
    int frames = 0, missed = 0;
    uint64_t total_frames = 0, total_missed = 0;
};

class Meter {
public:
    void wait_begin(double now_ms) {
        std::lock_guard<std::mutex> l(m_);
        wait_begin_ = now_ms;
    }
    void wait_end(double now_ms, int64_t period_ns) {
        std::lock_guard<std::mutex> l(m_);
        waits_++;
        // The last wait was never followed by a frame handed in that we saw: still a frame the headset got (the
        // wait-to-wait time is the frame time), so it is kept with its work unknown (-1). Seen 2026-11-21 in Silent
        // Hill 2 with the real headset: some starts showed waits and no hand-ins, and the meter wrote nothing.
        if (armed_) {
            unended_++;
            push_row(-1.0);
        }
        if (t0_ < 0) t0_ = now_ms;
        prev_end_ = cur_end_;
        cur_end_ = now_ms;
        cur_wait_ = wait_begin_ >= 0 ? now_ms - wait_begin_ : 0;
        if (period_ns > 0) period_ms_ = period_ns / NS_PER_MS;
        armed_ = true;
    }
    // The game handed the frame in: one row. A frame handed in without a wait before it (a game that skips the
    // wait) makes no row.
    void frame_end(double now_ms) {
        std::lock_guard<std::mutex> l(m_);
        ends_++;
        if (!armed_) {
            orphan_ends_++;
            return;
        }
        push_row(now_ms - cur_end_);
    }
    // Counters for finding out why a meter saw no frames: waits, hand-ins, hand-ins with no wait before them, waits
    // with no hand-in after them.
    uint64_t waits() { std::lock_guard<std::mutex> l(m_); return waits_; }
    uint64_t ends() { std::lock_guard<std::mutex> l(m_); return ends_; }
    uint64_t orphan_ends() { std::lock_guard<std::mutex> l(m_); return orphan_ends_; }
    uint64_t unended() { std::lock_guard<std::mutex> l(m_); return unended_; }

private:
    // One row for the frame the last wait opened (the lock is held by the caller).
    void push_row(double work_ms) {
        armed_ = false;
        Row r{};
        r.t_ms = cur_end_ - t0_;
        r.interval_ms = prev_end_ >= 0 ? cur_end_ - prev_end_ : 0;
        r.wait_ms = cur_wait_;
        r.work_ms = work_ms;
        r.period_ms = period_ms_;
        r.missed = (period_ms_ > 0 && r.interval_ms > MISSED_FACTOR * period_ms_) ? 1 : 0;
        pending_.push_back(r);
        window_.push_back(r);
        while (!window_.empty() && window_.front().t_ms < r.t_ms - LIVE_WINDOW_MS) window_.pop_front();
        total_++;
        total_missed_ += r.missed;
    }

public:
    // The rows since the last call, for the file.
    std::vector<Row> take_rows() {
        std::lock_guard<std::mutex> l(m_);
        std::vector<Row> out(pending_.begin(), pending_.end());
        pending_.clear();
        return out;
    }
    Live live() {
        std::lock_guard<std::mutex> l(m_);
        Live v;
        v.period_ms = period_ms_;
        v.total_frames = total_;
        v.total_missed = total_missed_;
        double span = 0;
        for (const Row& r : window_) {
            if (r.interval_ms <= 0) continue;
            v.frames++;
            v.missed += r.missed;
            span += r.interval_ms;
            if (r.interval_ms > v.worst_ms) v.worst_ms = r.interval_ms;
        }
        v.fps = span > 0 ? v.frames * 1000.0 / span : 0;
        return v;
    }
    void reset() {
        std::lock_guard<std::mutex> l(m_);
        *this = Meter();
    }
    Meter() = default;
    Meter& operator=(const Meter& o) {   // only used by reset(): the mutex itself is never copied
        if (this != &o) {
            wait_begin_ = o.wait_begin_; prev_end_ = o.prev_end_; cur_end_ = o.cur_end_; cur_wait_ = o.cur_wait_;
            t0_ = o.t0_; period_ms_ = o.period_ms_; armed_ = o.armed_; pending_ = o.pending_; window_ = o.window_;
            total_ = o.total_; total_missed_ = o.total_missed_;
            waits_ = o.waits_; ends_ = o.ends_; orphan_ends_ = o.orphan_ends_; unended_ = o.unended_;
        }
        return *this;
    }

private:
    std::mutex m_;
    double wait_begin_ = -1, prev_end_ = -1, cur_end_ = -1, cur_wait_ = 0, t0_ = -1, period_ms_ = 0;
    bool armed_ = false;
    std::deque<Row> pending_, window_;
    uint64_t total_ = 0, total_missed_ = 0, waits_ = 0, ends_ = 0, orphan_ends_ = 0, unended_ = 0;
};

inline const char* csv_header() { return "t_ms,interval_ms,wait_ms,work_ms,period_ms,missed\n"; }

inline std::string csv_line(const Row& r) {
    char b[160];
    snprintf(b, sizeof b, "%.3f,%.3f,%.3f,%.3f,%.3f,%d\n", r.t_ms, r.interval_ms, r.wait_ms, r.work_ms, r.period_ms,
             r.missed);
    return b;
}

inline std::string live_json(const Live& v, const char* exe, double now_unix_s) {
    char b[400];
    snprintf(b, sizeof b,
             "{\"exe\": \"%s\", \"updated\": %.3f, \"fps\": %.2f, \"hz\": %.2f, \"period_ms\": %.3f, "
             "\"frames\": %d, \"missed\": %d, \"worst_ms\": %.3f, \"total_frames\": %llu, \"total_missed\": %llu}\n",
             exe, now_unix_s, v.fps, v.period_ms > 0 ? 1000.0 / v.period_ms : 0.0, v.period_ms, v.frames, v.missed,
             v.worst_ms, (unsigned long long)v.total_frames, (unsigned long long)v.total_missed);
    return b;
}

// The settings file beside the layer (lanes_tune_meter.txt): "on = 1" and "exe = game.exe, other.exe" (or "*").
struct Settings {
    int on = 0;
    std::vector<std::string> exes;
    std::string out;
};

inline std::string trim(const std::string& s) {
    size_t a = s.find_first_not_of(" \t\r\n"), b = s.find_last_not_of(" \t\r\n");
    return a == std::string::npos ? std::string() : s.substr(a, b - a + 1);
}

inline std::string lower(std::string s) {
    for (char& c : s) if (c >= 'A' && c <= 'Z') c = char(c - 'A' + 'a');
    return s;
}

inline Settings parse_settings(const std::string& text) {
    Settings s;
    size_t pos = 0;
    while (pos <= text.size()) {
        size_t nl = text.find('\n', pos);
        std::string line = text.substr(pos, nl == std::string::npos ? std::string::npos : nl - pos);
        pos = nl == std::string::npos ? text.size() + 1 : nl + 1;
        line = trim(line);
        if (line.empty() || line[0] == '#') continue;
        size_t eq = line.find('=');
        if (eq == std::string::npos) continue;
        std::string k = lower(trim(line.substr(0, eq))), v = trim(line.substr(eq + 1));
        if (k == "on") s.on = atoi(v.c_str());
        else if (k == "out") s.out = v;
        else if (k == "exe") {
            size_t p = 0;
            while (p <= v.size()) {
                size_t c = v.find(',', p);
                std::string one = lower(trim(v.substr(p, c == std::string::npos ? std::string::npos : c - p)));
                if (!one.empty()) s.exes.push_back(one);
                p = c == std::string::npos ? v.size() + 1 : c + 1;
            }
        }
    }
    return s;
}

// exe_path is the game's full program path; matched on its file name, without case.
inline bool exe_matches(const Settings& s, const std::string& exe_path) {
    size_t cut = exe_path.find_last_of("\\/");
    std::string name = lower(cut == std::string::npos ? exe_path : exe_path.substr(cut + 1));
    for (const std::string& e : s.exes)
        if (e == "*" || e == name) return true;
    return false;
}

}  // namespace tm_meter
