"""tour_test.py - the tour: the look-around on a spot, the shared measuring window, the spots list, the step machine,
apply, the result and undo. Made-up meter recordings, a pretend game, a temp folder; nothing real is touched.
Exit 0 = pass. Each test is a function named as the plan names it."""
import json
import math
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
fails = 0
T = tempfile.mkdtemp(prefix="optimizer-tour-")
os.environ["OPTIMIZER_DIR"] = os.path.join(T, "optimizer")
os.environ["OPTIMIZER_SIM_DATA"] = os.path.join(T, "sim")
os.environ["OPTIMIZER_NO_GPU"] = "1"
os.environ["OPTIMIZER_RUNTIME"] = "virtualdesktop"
os.environ["OPTIMIZER_LANES_CONF"] = os.path.join(T, "lanes.conf")


def check(ok, what):
    global fails
    print(("  ok    " if ok else "FAIL: ") + what)
    fails += not ok


def make_csv(path, frames, late_every=0, work=4.0, period=13.889):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("# test\nt_ms,interval_ms,wait_ms,work_ms,period_ms,missed\n")
        t = 0.0
        for i in range(frames):
            iv = period * 2 if late_every and i % late_every == 0 else period
            t += iv
            f.write(f"{t:.3f},{iv:.3f},2.0,{work:.3f},{period:.3f},{int(iv > 1.5 * period)}\n")
    return path


# ---- Task 4: the look-around and the measuring window ----------------------------------------------------------
def look_writes_twelve_heads():
    from engine import look as L
    from engine import settings as S
    S.LOOK_STEP_S = 0
    written = []
    real = L.head

    def spy(x, y, z, yaw_deg, pitch_deg=0):
        ok = real(x, y, z, yaw_deg, pitch_deg)
        with open(os.path.join(os.environ["OPTIMIZER_SIM_DATA"], "head_pose_command.json"), encoding="utf-8") as f:
            written.append(json.load(f))
        return ok

    L.head = spy
    try:
        L.look_around()
    finally:
        L.head = real
    yaws = [round(w["yaw"], 6) for w in written]
    check(len(written) == S.LOOK_STEPS == 12, "look_writes_twelve_heads: twelve head poses")
    check(yaws == [round(math.radians(30 * i), 6) for i in range(12)], "look_writes_twelve_heads: 0, 30 ... 330 in radians")
    check(all(abs(w["y"] - S.LOOK_HEIGHT_M) < 1e-9 and w["pitch"] == 0 and w["roll"] == 0 for w in written),
          "look_writes_twelve_heads: at standing height, level")
    left = [n for n in os.listdir(os.environ["OPTIMIZER_SIM_DATA"]) if n != "head_pose_command.json"]
    check(left == [], "look_writes_twelve_heads: no temp file left behind (written whole, then replaced)")


def measure_window_from_a_recording():
    from engine import read as R
    path = make_csv(os.path.join(T, "rec", "heavy.csv"), 720, late_every=10)
    rows, gpu, why = R.measure_window("Pretend.exe", 5, csv=path)
    check(why is None and gpu is None and rows and rows[-1]["t_ms"] - rows[0]["t_ms"] <= 5000,
          "measure_window: the last 5 s of a recording")


TESTS = [look_writes_twelve_heads, measure_window_from_a_recording]


def main():
    only = sys.argv[1:]
    for t in TESTS:
        if not only or t.__name__ in only:
            t()
    print("tour_test: " + ("all passed" if not fails else f"{fails} FAILED"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
