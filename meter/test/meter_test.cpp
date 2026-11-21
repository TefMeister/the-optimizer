// meter_test.cpp -- the frame meter's counting, with made-up clocks: no OpenXR, no game. Exit 0 = pass.
#include "../src/meter_core.h"

#include <cmath>
#include <cstdio>

static int fails = 0;
static void check(bool ok, const char* what) {
    printf("%s%s\n", ok ? "  ok    " : "FAIL: ", what);
    fails += !ok;
}

int main() {
    using namespace tm_meter;
    const int64_t period_ns = 13888889;   // 72 Hz
    Meter m;
    double t = 1000;
    // 144 smooth frames at 72 Hz: the game waits 8 ms, works 5 ms
    for (int i = 0; i < 144; i++) {
        m.wait_begin(t);
        m.wait_end(t + 8.0, period_ns);
        m.frame_end(t + 13.0);
        t += 13.888889;
    }
    // one hitch: the next wait returns two periods late
    m.wait_begin(t);
    m.wait_end(t + 8.0 + 13.888889, period_ns);
    m.frame_end(t + 8.0 + 13.888889 + 5.0);
    auto rows = m.take_rows();
    check(rows.size() == 145, "one row per frame handed in");
    check(rows[0].interval_ms == 0, "the first frame has no interval");
    check(std::fabs(rows[1].interval_ms - 13.888889) < 0.01, "a smooth frame's interval is one period");
    check(std::fabs(rows[1].wait_ms - 8.0) < 0.01 && std::fabs(rows[1].work_ms - 5.0) < 0.01, "wait and work split");
    check(rows[1].missed == 0 && rows.back().missed == 1, "the hitch is marked missed, a smooth frame is not");
    check(m.take_rows().empty(), "rows are taken once");
    Live v = m.live();
    check(std::fabs(1000.0 / v.period_ms - 72.0) < 0.01, "the headset rate comes from the runtime's period");
    check(v.missed == 1 && v.total_missed == 1 && v.total_frames == 145, "the live summary counts the hitch");
    check(v.fps > 68 && v.fps < 72, "two seconds with one hitch: just under 72 frames a second");
    // a frame handed in with no wait before it makes no row
    m.frame_end(t + 100);
    check(m.take_rows().empty(), "no wait, no row");
    // settings
    Settings s = parse_settings("# comment\non = 1\nexe = Cemu.exe, SHProto-Win64-Shipping.exe\n");
    check(s.on == 1 && s.exes.size() == 2, "settings read");
    check(exe_matches(s, "C:\\Games\\Breath of the Wild VR\\cemu.exe"), "exe matched by name, without case");
    check(!exe_matches(s, "C:\\Other\\game.exe"), "another game is left alone");
    check(exe_matches(parse_settings("on=1\nexe=*"), "x:\\any.exe"), "exe = * means every game");
    check(parse_settings("exe = *").on == 0, "off unless on = 1");
    // waits with no hand-in seen (2026-11-21, Silent Hill 2 with the real headset): each frame still gets a row from
    // the wait-to-wait time, its work unknown
    Meter w;
    for (int i = 0; i < 10; i++) { w.wait_begin(i * 13.888889); w.wait_end(i * 13.888889 + 1.0, 13888889); }
    const auto wr = w.take_rows();
    check(wr.size() == 9 && std::fabs(wr[1].interval_ms - 13.888889) < 0.01 && wr[1].work_ms < 0,
          "waits with no hand-in still give one row a frame, work unknown");
    check(w.waits() == 10 && w.ends() == 0 && w.unended() == 9, "the counters say the hand-ins were not seen");
    w.frame_end(500); w.frame_end(501);
    check(w.ends() == 2 && w.orphan_ends() == 1, "a hand-in with no wait before it is counted apart");
    const std::string line = csv_line(rows.back());
    check(line.find(",1\n") != std::string::npos, "a missed row ends in 1");
    printf(fails ? "meter_test: %d FAILED\n" : "meter_test: all passed\n", fails);
    return fails ? 1 : 0;
}
