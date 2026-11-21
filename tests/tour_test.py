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
os.environ["OPTIMIZER_UEVR_BASE"] = "http://127.0.0.1:9"      # no connector answers there
os.environ["OPTIMIZER_FAKE_RUNNING"] = "0"                     # the pretend game is closed unless a test says


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


# ---- Task 6: the tour's step machine ----------------------------------------------------------------------------
LIVE_KNOBS = [
    {"id": "rt", "label": "Ray-traced reflections", "kind": "live_cvar", "key": "r.RT", "steps": ["0", "1"],
     "default": 1, "floor": 0, "shows": 1, "cost": 3, "live": "uevr_http", "live_safe": True, "restart": False,
     "keep": None},
    {"id": "shadow", "label": "Shadow sharpness", "kind": "live_cvar", "key": "r.Shadow", "steps": ["1024", "1500"],
     "default": 1, "floor": 0, "shows": 1, "cost": 1, "live": "uevr_http", "live_safe": True, "restart": False,
     "keep": None},
]
RESTART_KNOB = {"id": "dlss", "label": "DLSS level", "kind": "ini", "file": "", "key": "DLSS", "steps": ["1", "2", "3"],
                "default": 1, "floor": 0, "shows": 2, "cost": 3, "restart": True, "keep": None}
RECS = {}


def _recs():
    if not RECS:
        from engine import read as R
        RECS["smooth"] = R.read_meter_csv(make_csv(os.path.join(T, "rec", "smooth.csv"), 720))
        RECS["heavy"] = R.read_meter_csv(make_csv(os.path.join(T, "rec", "heavy.csv"), 720, late_every=10))
    return RECS["smooth"], RECS["heavy"]


def _pack(game, nslots, knobs=None, godmode=None):
    p = _saves(range(nslots), "tour-" + game)
    ini = os.path.join(T, "ini-" + game, "game.ini")
    os.makedirs(os.path.dirname(ini), exist_ok=True)
    open(ini, "w").close()
    ks = [dict(k) for k in (knobs if knobs is not None else LIVE_KNOBS)]
    for k in ks:
        if k.get("kind") == "ini":
            k["file"] = ini
    p.update({"name": game, "exe": "Pretend-Win64-Shipping.exe", "settings": {"knobs": ks}, "godmode": godmode,
              "settle": 0})
    return p


def drive(game, judge, limit=400, stop_at=None):
    """Answer each step the way the toolbox will. judge(spot, levels) -> (rows, gpu), "crash" or "die".
    Returns every step seen; stops at a step named in stop_at, or at the first step it has no answer for."""
    from engine import tour as TR
    seen = []
    for _ in range(limit):
        st = TR.next_step(game)
        seen.append(st)
        do = st["do"]
        if stop_at and do in stop_at:
            return seen
        if do == "reach":
            TR.arrived(game)
        elif do == "settle_wait":
            TR.settled(game)
        elif do == "godmode":
            TR.godmode_on(game)
        elif do == "look_and_measure":
            tour = TR.load(game)
            r = judge(tour["at"], tour["levels"])
            if r == "crash":
                TR.crashed(game)
            elif r == "die":
                TR.died(game)
            else:
                TR.measured(game, *r)
        elif do == "set":
            TR.changed(game, st["knob"], st["to"])
        elif do == "connector_cost":
            TR.cost(game, 14.0, 14.0)
        else:
            return seen
    raise AssertionError("the tour did not finish")


def rank_picks_worst_card_bound():
    from engine import decide as D
    from engine import read as R
    from engine import tour as TR
    smooth, heavy = _recs()
    mild = R.read_meter_csv(make_csv(os.path.join(T, "rec", "mild.csv"), 720, late_every=40))
    spots = {}
    for sid, rows, load in (("a", mild, 97), ("b", heavy, 96), ("c", heavy, 50), ("d", smooth, 70)):
        summ, gpu = R.summarize(rows, 72), {"load_avg": load}
        spots[sid] = {"status": "done", "last": {"summary": summ, "gpu": gpu, "verdict": D.verdict(summ, gpu)}}
    spot, cpu = TR.rank({"spots": spots})
    check(spot == "b" and cpu == ["c"], "rank_picks_worst_card_bound: the worst card-limited spot; the processor one apart")


def all_processor_bound_changes_nothing():
    from engine import tour as TR
    smooth, heavy = _recs()
    TR.begin("t6a", _pack("t6a", 3), build="b1")
    drive("t6a", lambda spot, lv: (heavy, {"load_avg": 50}), stop_at={"apply_all"})
    tour = TR.load("t6a")
    check(tour["phase"] == "applying" and tour["changes"] == []
          and sorted(tour["processor"]) == ["slot0", "slot1", "slot2"],
          "all_processor_bound_changes_nothing: nothing changed, every spot on the processor list")
    check(all("settings can't fix this" in TR.spot_words(tour, sid) for sid in tour["processor"]),
          "all_processor_bound_changes_nothing: each named 'settings can't fix this'")


def short_measure_is_not_ranked():
    from engine import tour as TR
    smooth, heavy = _recs()
    TR.begin("t6b", _pack("t6b", 2), build="b1")
    short = heavy[:100]
    drive("t6b", lambda spot, lv: (short, {"load_avg": 97}) if spot == "slot0" else (smooth, {"load_avg": 60}),
          stop_at={"set", "apply_all"})
    tour = TR.load("t6b")
    check(tour["spots"]["slot0"]["last"]["verdict"]["result"] == "short" and tour["tuning_spot"] != "slot0",
          "short_measure_is_not_ranked: a too-short measure is never the tuning spot")


def crash_retry_then_unreachable():
    from engine import tour as TR
    smooth, _ = _recs()
    TR.begin("t6c", _pack("t6c", 2), build="b1")
    seen = drive("t6c", lambda spot, lv: "crash" if spot == "slot0" else (smooth, {"load_avg": 60}),
                 stop_at={"set", "apply_all"})
    reaches = [s for s in seen if s["do"] == "reach" and s["spot"] == "slot0"]
    check(len(reaches) == 2 and TR.load("t6c")["spots"]["slot0"]["status"] == "unreachable",
          "crash_retry_then_unreachable: one retry, then unreachable")


def died_twice_is_unsafe():
    from engine import tour as TR
    smooth, _ = _recs()
    TR.begin("t6d", _pack("t6d", 2, godmode={"console": "god"}), build="b1")
    seen = drive("t6d", lambda spot, lv: "die" if spot == "slot0" else (smooth, {"load_avg": 60}),
                 stop_at={"set", "apply_all"})
    order = [s["do"] for s in seen if s.get("spot") == "slot1"]
    tour = TR.load("t6d")
    check(tour["spots"]["slot0"]["status"] == "unsafe" and tour["spots"]["slot0"]["deaths"] == 2,
          "died_twice_is_unsafe: two deaths, unsafe")
    check("godmode" in order and order.index("godmode") < order.index("look_and_measure"),
          "died_twice_is_unsafe: with a pack god mode, it is asked for before the look")


def final_lap_two_rounds_max():
    from engine import tour as TR
    smooth, heavy = _recs()
    TR.begin("t6e", _pack("t6e", 2), build="b1")
    drive("t6e", lambda spot, lv: (heavy, {"load_avg": 97}) if spot == "slot1" else (smooth, {"load_avg": 60}),
          stop_at={"apply_all"})
    tour = TR.load("t6e")
    check(tour["phase"] == "applying" and tour["round"] == 2, "final_lap_two_rounds_max: two rounds, then apply")


def tour_resumes_mid_spot():
    import importlib
    from engine import tour as TR
    TR.begin("t6f", _pack("t6f", 2), build="b1")
    TR.next_step("t6f")
    TR.arrived("t6f")
    TR.settled("t6f")
    importlib.reload(TR)
    st = TR.next_step("t6f")
    check(st["do"] == "look_and_measure" and st["spot"] == "slot0",
          "tour_resumes_mid_spot: after a restart of the toolbox it carries on at the same spot and step")


def strike_mid_tour():
    from engine import spots as SP
    from engine import tour as TR
    smooth, _ = _recs()
    TR.begin("t6g", _pack("t6g", 3), build="b1")
    TR.next_step("t6g")
    TR.arrived("t6g")
    SP.strike("t6g", "slot0")
    st = TR.next_step("t6g")
    check(st["do"] == "reach" and st["spot"] == "slot1", "strike_mid_tour: a spot struck while there is left at once")
    drive("t6g", lambda spot, lv: (smooth, {"load_avg": 60}), stop_at={"set", "apply_all"})
    check(TR.load("t6g")["spots"]["slot0"].get("last") is None, "strike_mid_tour: and never measured")


def cost_below_noise_subtracts_nothing():
    from engine import tour as TR
    TR.begin("t6h", _pack("t6h", 1), build="b1")
    TR.cost("t6h", 14.10, 14.0)
    tour = TR.load("t6h")
    check(tour["connector_ms"] == 0.0 and "under the noise" in tour["connector_say"],
          "cost_below_noise_subtracts_nothing: 0.1 ms is under the noise, nothing subtracted")


def cost_above_noise_is_subtracted():
    from engine import read as R
    from engine import tour as TR
    TR.begin("t6i", _pack("t6i", 1), build="b1")
    TR.cost("t6i", 15.0, 14.0)
    tour = TR.load("t6i")
    near = R.read_meter_csv(make_csv(os.path.join(T, "rec", "near.csv"), 720, work=13.5))
    adj = TR.adjusted(tour, R.summarize(near, 72))
    check(abs(tour["connector_ms"] - 1.0) < 1e-9 and abs(adj["work_p95_ms"] - 12.5) < 1e-6,
          "cost_above_noise_is_subtracted: 1.0 ms taken off the game's own work")
    TR.begin("t6i", _pack("t6i", 1), build="b1")
    check(TR.load("t6i")["connector_ms"] == 1.0, "the cost is measured once per game and build: kept for the same build")
    TR.begin("t6i", _pack("t6i", 1), build="b2")
    check(TR.load("t6i")["connector_ms"] is None, "a new build of the game: measured again")


def restart_only_settings_come_last():
    from engine import tour as TR
    smooth, heavy = _recs()
    TR.begin("t6j", _pack("t6j", 1, knobs=LIVE_KNOBS + [RESTART_KNOB]), build="b1")

    def judge(spot, lv):
        return (smooth, {"load_avg": 60}) if lv["dlss"] == 0 else (heavy, {"load_avg": 97})
    seen = drive("t6j", judge, stop_at={"apply_all"})
    sets = [s["knob"] for s in seen if s["do"] == "set"]
    restarts = [s for s in seen if s["do"] == "reach" and s.get("restart")]
    check(sets[:3] == ["rt", "shadow", "dlss"], f"restart_only_settings_come_last: live ones first ({sets})")
    check(bool(restarts), "restart_only_settings_come_last: a restart-only change is followed by a relaunch and a reach")


def markers_written_per_look():
    import glob
    from engine import settings as S
    from engine import tour as TR
    smooth, _ = _recs()
    import shutil
    shutil.rmtree(S.meter_dir(), ignore_errors=True)       # the other tests' markers are not this one's
    TR.begin("t6k", _pack("t6k", 2), build="b1")
    drive("t6k", lambda spot, lv: (smooth, {"load_avg": 60}), stop_at={"set", "apply_all"})
    files = glob.glob(os.path.join(S.meter_dir(), "*_Pretend-Win64-Shipping.frametime-spots.tsv"))
    lines = open(files[0], encoding="utf-8").read().splitlines() if len(files) == 1 else []
    rows = [ln.split("\t") for ln in lines[1:]]
    measured = [r[1] for r in rows if r[2] == "measured"]
    check(len(files) == 1 and lines[0] == "t_unix\tspot\tevent\tsettings" and measured[:2] == ["slot0", "slot1"]
          and all("rt=" in r[3] for r in rows), "markers_written_per_look: one marker file, a line per look with the settings")


def live_change_away_from_tuning_spot_reaches_it_first():
    """Found by the dry run (2026-11-21): after the visits the game stands at the LAST spot, not the tuning spot, so a
    live change must be followed by going to the tuning spot, never by a measure where the game happens to be."""
    from engine import tour as TR
    smooth, heavy = _recs()
    TR.begin("t6l", _pack("t6l", 2), build="b1")
    seen = drive("t6l", lambda spot, lv: (heavy, {"load_avg": 97}) if spot == "slot0" else (smooth, {"load_avg": 60}),
                 stop_at={"set"})
    TR.changed("t6l", seen[-1]["knob"], seen[-1]["to"])
    st = TR.next_step("t6l")
    check(st["do"] == "reach" and st["spot"] == "slot0" and st["restart"],
          "live_change_away_from_tuning_spot_reaches_it_first: back to the tuning spot (a relaunch), then measure")
    TR.arrived("t6l")
    TR.settled("t6l")
    smooth_rows, _ = _recs()
    TR.measured("t6l", smooth_rows, {"load_avg": 60})
    st = TR.next_step("t6l")
    if st["do"] == "set":
        TR.changed("t6l", st["knob"], st["to"])
        st = TR.next_step("t6l")
        check(st["do"] == "settle_wait" and st["spot"] == "slot0",
              "and a live change made while standing at the tuning spot is measured right there")
    else:
        check(False, f"expected a second change, got {st['do']}")


# ---- Task 7: apply, the result, undo ---------------------------------------------------------------------------
def _finished(game, nslots=1, judge=None):
    """A tour driven to 'applying', with one setting the game keeps in a file (dlss) and two live-only ones."""
    from engine import tour as TR
    smooth, heavy = _recs()
    knobs = LIVE_KNOBS + [dict(RESTART_KNOB)]
    p = _pack(game, nslots, knobs=knobs)
    for k in p["settings"]["knobs"]:
        if k["id"] == "dlss":
            k["keep"] = k["file"]
            with open(k["file"], "w", encoding="utf-8", newline="") as f:
                f.write("[Graphics]\r\nDLSS=2\r\nVSync=0\r\n")
    TR.begin(game, p, build="b1")
    drive(game, judge or (lambda spot, lv: (smooth, {"load_avg": 60}) if lv["dlss"] == 0 else (heavy, {"load_avg": 97})),
          stop_at={"apply_all"})
    return p, [k for k in p["settings"]["knobs"] if k["id"] == "dlss"][0]["file"]


def apply_reports_live_only():
    from engine import finish as F
    from engine import tour as TR
    _, ini = _finished("t7a")
    lines = F.apply("t7a")
    tour = TR.load("t7a")
    live = [ln for ln in lines if "holds only while you re-apply it" in ln]
    check(len(live) == 2 and any("Ray-traced reflections" in ln for ln in live),
          "apply_reports_live_only: the two live-only settings are said to hold only while re-applied")
    check(list(tour["applied"]) == ["dlss"] and "DLSS=1" in open(ini, newline="").read(),
          "apply_reports_live_only: only the file setting counts as applied, and it is written")
    check(tour["phase"] == "done", "apply_reports_live_only: the tour is done")


def apply_refused_while_running():
    from engine import finish as F
    _, ini = _finished("t7e")
    os.environ["OPTIMIZER_FAKE_RUNNING"] = "1"
    try:
        lines = F.apply("t7e")
    finally:
        os.environ["OPTIMIZER_FAKE_RUNNING"] = "0"
    check("close it" in " ".join(lines) and "DLSS=2" in open(ini, newline="").read(),
          "apply waits for the game to be closed (it would write its own settings over ours)")


def apply_reports_undone_setting():
    from engine import finish as F
    _, ini = _finished("t7b")
    F.apply("t7b")
    with open(ini, "w", newline="") as f:                     # the game wrote its own value back at its start
        f.write("[Graphics]\r\nDLSS=2\r\nVSync=0\r\n")
    lines = F.check_applied("t7b")
    check(any("DLSS level" in ln and "did not stick" in ln for ln in lines),
          "apply_reports_undone_setting: a setting the game undid is said not to have stuck")
    F.apply("t7b")
    check(not any("did not stick" in ln for ln in F.check_applied("t7b")), "and one that stuck is not")


def result_lists_everything():
    from engine import finish as F
    smooth, heavy = _recs()

    def judge(spot, lv):
        if spot == "slot1":
            return (heavy, {"load_avg": 50})
        if spot == "slot2":
            return "crash"
        if spot == "slot3":
            return "die"
        return (smooth, {"load_avg": 60}) if lv["dlss"] == 0 else (heavy, {"load_avg": 97})
    _finished("t7c", nslots=4, judge=judge)
    F.apply("t7c")
    lines = F.result("t7c")
    text = "\n".join(lines)
    check(os.path.isfile(os.path.join(os.environ["OPTIMIZER_DIR"], "t7c", "result.txt")),
          "result_lists_everything: result.txt written")
    check("The spots, worst first" in text and "save slot 0" in text, "result_lists_everything: the spots ranked")
    check("DLSS level: 2 -> 1" in text and "costs in looks: some" in text,
          "result_lists_everything: each setting with what it costs in looks")
    check("settings can't fix these" in text and "short by" in text, "result_lists_everything: the processor list")
    check("could not be reached" in text and "unsafe" in text, "result_lists_everything: unreachable and unsafe spots")
    check("Measured with" in text and "pretend headset" in text, "result_lists_everything: what was measured with")


def undo_restores_every_file():
    from engine import finish as F
    _, ini = _finished("t7d")
    before = open(ini, newline="").read()
    F.apply("t7d")
    lines = F.undo("t7d")
    check(open(ini, newline="").read() == before and any("restored" in ln for ln in lines),
          "undo_restores_every_file: the game's file is back byte for byte")


TESTS = [look_writes_twelve_heads, measure_window_from_a_recording, find_lists_every_slot, find_twice_adds_none,
         person_add_and_strike, find_after_slots_change, rank_picks_worst_card_bound,
         all_processor_bound_changes_nothing, short_measure_is_not_ranked, crash_retry_then_unreachable,
         died_twice_is_unsafe, final_lap_two_rounds_max, tour_resumes_mid_spot, strike_mid_tour,
         cost_below_noise_subtracts_nothing, cost_above_noise_is_subtracted, restart_only_settings_come_last,
         markers_written_per_look, live_change_away_from_tuning_spot_reaches_it_first, apply_reports_live_only, apply_refused_while_running,
         apply_reports_undone_setting, result_lists_everything, undo_restores_every_file]


def main():
    only = sys.argv[1:]
    for t in TESTS:
        if not only or t.__name__ in only:
            t()
    print("tour_test: " + ("all passed" if not fails else f"{fails} FAILED"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
