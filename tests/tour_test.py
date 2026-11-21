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


# ---- Task 5: the spots list ------------------------------------------------------------------------------------
def _saves(n, folder="saves"):
    d = os.path.join(T, folder, "SaveGames", "1234")
    os.makedirs(d, exist_ok=True)
    for name in os.listdir(d):
        os.remove(os.path.join(d, name))
    for i in n:
        with open(os.path.join(d, f"SaveGameData_{i}.sav"), "wb") as f:
            f.write(b"save %d" % i)
    return {"name": "pretend", "spots_find": {"save_glob": os.path.join(T, folder, "SaveGames", "*", "SaveGameData_*.sav"),
                                              "slot_re": r"SaveGameData_(\d+)\.sav$", "reach": "save_slot"}}


def find_lists_every_slot():
    from engine import spots as SP
    pack = _saves(range(7), "s1")
    added = SP.find("g1", pack)
    sp = SP.load("g1")
    check(added == 7 and [s["id"] for s in sp] == [f"slot{i}" for i in range(7)],
          "find_lists_every_slot: slot0 .. slot6")
    check(sp[3]["label"] == "save slot 3 (not named yet)" and sp[3]["by"] == "robot" and not sp[3]["struck"]
          and sp[3]["reach"] == {"kind": "save_slot", "value": 3}, "find_lists_every_slot: each says how it is reached")


def find_twice_adds_none():
    from engine import spots as SP
    pack = _saves(range(7), "s2")
    SP.find("g2", pack)
    check(SP.find("g2", pack) == 0 and len(SP.load("g2")) == 7, "find_twice_adds_none")


def person_add_and_strike():
    from engine import spots as SP
    pack = _saves(range(2), "s3")
    SP.find("g3", pack)
    sid = SP.add("g3", "the hotel lobby", "console", "open Hotel_Lobby")
    SP.strike("g3", "slot1")
    SP.name("g3", "slot0", "the prison armory")
    sp = {s["id"]: s for s in SP.load("g3")}
    check(sp[sid]["by"] == "person" and sp[sid]["reach"] == {"kind": "console", "value": "open Hotel_Lobby"},
          "person_add_and_strike: a spot added by the person")
    check(sp["slot1"]["struck"] and [s["id"] for s in SP.active("g3")] == ["slot0", sid],
          "person_add_and_strike: a struck spot is not visited")
    check(sp["slot0"]["label"] == "the prison armory", "person_add_and_strike: a spot can be named")


def find_after_slots_change():
    from engine import spots as SP
    pack = _saves([0, 1, 2], "s4")
    SP.find("g4", pack)
    SP.strike("g4", "slot1")
    SP.name("g4", "slot0", "the armory")
    pack = _saves([0, 1, 3, 4], "s4")            # slot 2 is gone, slots 3 and 4 are new
    added = SP.find("g4", pack)
    sp = {s["id"]: s for s in SP.load("g4")}
    check(added == 2 and "slot3" in sp and "slot4" in sp, "find_after_slots_change: the new slots are added")
    check(sp["slot1"]["struck"] and sp["slot0"]["label"] == "the armory",
          "find_after_slots_change: the person's strike and name are kept")
    check("slot2" not in [s["id"] for s in SP.active("g4")], "find_after_slots_change: a vanished slot is never measured")
    _saves([0, 1, 2, 3, 4], "s4")
    SP.find("g4", pack)
    check("slot2" in [s["id"] for s in SP.active("g4")], "find_after_slots_change: and comes back when its file does")


TESTS = [look_writes_twelve_heads, measure_window_from_a_recording, find_lists_every_slot, find_twice_adds_none,
         person_add_and_strike, find_after_slots_change]


def main():
    only = sys.argv[1:]
    for t in TESTS:
        if not only or t.__name__ in only:
            t()
    print("tour_test: " + ("all passed" if not fails else f"{fails} FAILED"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
