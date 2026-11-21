"""tour.py - the tour's step machine: visit every spot, rank them, tune at the worst one the graphics card limits, prove
the result on every spot, then hand over to apply (the design's 5.4, steps 2 to 7).

The machine never touches the game. It says what to do next (next_step), and is told what happened (arrived,
settled, godmode_on, measured, crashed, died, changed, cost). Everything is kept in <OPTIMIZER_DIR>/<game>/tour.json
after every event, so a toolbox that is restarted carries on at the same spot and step.

Phases: visiting -> cost (the connector's own cost, once per game and build) -> tuning -> final (the final lap, at most
FINAL_LAP_ROUNDS rounds) -> applying -> done; "stopped" when a stop rule fired.
Per spot: reach -> settle -> (god mode, when the pack has one) -> look (the look-around and the measure).
"""
import json
import os
import time

from engine import decide as D
from engine import knobs as K
from engine import read as R
from engine import settings as C
from engine import spots as SP


# ---- the file --------------------------------------------------------------------------------------------------
def _path(game):
    return os.path.join(C.game_dir(game), "tour.json")


def _cost_path(game):
    return os.path.join(C.game_dir(game), "connector_cost.json")


def load(game):
    try:
        with open(_path(game), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        raise SystemExit(f"optimizer: no tour has been started for '{game}'")


def save(game, tour):
    os.makedirs(C.game_dir(game), exist_ok=True)
    tmp = _path(game) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(tour, f, indent=1)
    os.replace(tmp, _path(game))


def _entry(tour, sid):
    return tour["spots"].setdefault(sid, {"status": "todo", "crashes": 0, "deaths": 0, "god": False})


def _knobs(tour):
    return {k["id"]: k for k in tour["knobs"]}


# ---- starting --------------------------------------------------------------------------------------------------
def begin(game, pack, build=None, headset=False, exe=None):
    """A new tour: finds the spots, reads every setting's start value, keeps the connector's cost for this build."""
    SP.find(game, pack)
    knobs = [k for k in (pack.get("settings") or {}).get("knobs", []) if k.get("kind") != "ask"]
    exe = exe or pack.get("exe", "")
    levels = {}
    for k in knobs:
        val, _src = K.start_value(k, {"exe": exe})
        i = K.step_index(k, val)
        if i is not None:
            levels[k["id"]] = i
    cost = {}
    try:
        with open(_cost_path(game), encoding="utf-8") as f:
            cost = json.load(f)
    except (OSError, ValueError):
        pass
    same = build is not None and cost.get("build") == build
    tour = {"game": game, "pack": pack.get("name", game), "exe": exe, "exe_stem": os.path.splitext(
                os.path.basename(exe))[0], "build": build, "headset": bool(headset),
            "target": float(pack.get("target", C.DEFAULT_TARGET_FPS)), "settle": pack.get("settle", 5),
            "godmode": pack.get("godmode"), "has_connector": bool(pack.get("connector")),
            "knobs": knobs, "levels": levels, "start": dict(levels), "ceilings": {}, "live_read": False,
            "phase": "visiting", "round": 0, "lap_done": [], "at": None, "step": "reach", "spots": {},
            "tuning_spot": None, "processor": [], "tune_verdict": None, "pending": None, "revert": None,
            "need_restart": False, "here": None, "steps": 0, "short_tries": 0, "changes": [],
            "connector_ms": cost.get("ms") if same else None, "connector_say": cost.get("say") if same else None,
            "stamp": time.strftime("%Y-%m-%d_%H-%M-%S"), "stop_why": None}
    save(game, tour)
    return tour


# ---- what to do next -------------------------------------------------------------------------------------------
def next_step(game):
    tour = load(game)
    for _ in range(8):                     # a phase change may need a second look; never loops for ever
        st = _next(game, tour)
        if st is not None:
            save(game, tour)
            return st
    raise SystemExit("optimizer: the tour could not decide its next step (a fault: please open an issue)")


def _spot_step(tour, game):
    sid = tour["at"]
    e = _entry(tour, sid)
    spot = SP.get(game, sid) or {"label": sid, "reach": None}
    e["label"] = spot["label"]
    base = {"spot": sid, "label": spot["label"]}
    if tour["step"] == "reach":
        return {"do": "reach", "reach": spot["reach"], "restart": bool(tour["need_restart"]),
                "say": f"go to {spot['label']}" + (" (restart the game first: a setting needs a start)"
                                                    if tour["need_restart"] else ""), **base}
    if tour["step"] == "settle":
        return {"do": "settle_wait", "seconds": tour["settle"], "say": f"wait until {spot['label']} is steady", **base}
    if tour["step"] == "god":
        if tour.get("godmode") and not e["god"]:
            return {"do": "godmode", "say": "switch god mode on before looking around", **tour["godmode"], **base}
        tour["step"] = "look"
    return {"do": "look_and_measure", "headset": tour["headset"],
            "say": f"look around at {spot['label']} and measure", **base}


def _next(game, tour):
    ph = tour["phase"]
    if ph == "stopped":
        return {"do": "stop", "say": "the tour stopped: " + (tour.get("stop_why") or "a stop rule fired")}
    if ph == "applying":
        return {"do": "apply_all", "say": "write every setting to where the game keeps it"}
    if ph == "done":
        return {"do": "finish", "say": "quit the game by its own quit, put the saves back, write the result"}
    if tour["revert"]:
        r = tour["revert"]
        k = _knobs(tour)[r["knob"]]
        return {"do": "set", "knob": r["knob"], "to": str(k["steps"][r["to"]]), "live": K.live_ok(k), "dir": "back",
                "say": f"put {k['label']} back to {K.shown(k, k['steps'][r['to']])}: the raise did not hold"}
    if ph == "cost":
        return {"do": "connector_cost", "spot": tour["tuning_spot"],
                "say": "measure the connector's own cost at the tuning spot (with it, then without it)"}
    active = [s["id"] for s in SP.active(game)]
    if tour["at"] and tour["at"] not in active:          # struck (or its save vanished) while there
        tour["at"], tour["step"] = None, "reach"
    if tour["at"]:
        return _spot_step(tour, game)
    if ph == "visiting":
        for sid in active:
            if _entry(tour, sid)["status"] == "todo":
                tour["at"], tour["step"] = sid, "reach"
                return _spot_step(tour, game)
        _after_visit(tour)
        return None
    if ph == "final":
        for sid in active:
            e = _entry(tour, sid)
            if e["status"] == "done" and sid not in tour["lap_done"]:
                tour["at"], tour["step"] = sid, "reach"
                return _spot_step(tour, game)
        _after_lap(tour)
        return None
    if ph == "tuning":
        return _tune(game, tour)
    raise SystemExit(f"optimizer: the tour is in a phase it does not know ({ph})")


def _after_visit(tour):
    spot, cpu = rank(tour)
    tour["tuning_spot"], tour["processor"] = spot, cpu
    if spot is None:
        tour["phase"] = "applying"
        return
    tour["tune_verdict"] = tour["spots"][spot]["last"]["verdict"]
    tour["phase"] = "cost" if tour["has_connector"] and tour["connector_ms"] is None else "tuning"


def _enter_final(tour):
    tour["phase"], tour["round"], tour["lap_done"] = "final", tour["round"] + 1, []


def _after_lap(tour):
    failing = _failing_card(tour, tour["lap_done"])
    tour["processor"] = sorted(set(tour["processor"]) | {sid for sid in tour["lap_done"] if _is_cpu(tour, sid)})
    if failing and tour["round"] < C.FINAL_LAP_ROUNDS:
        tour["tuning_spot"] = failing[0]
        tour["tune_verdict"] = tour["spots"][failing[0]]["last"]["verdict"]
        tour["phase"] = "tuning"
        return
    tour["phase"] = "applying"


def _tune(game, tour):
    if tour["steps"] >= C.MAX_STEPS:
        tour["changes"].append({"note": f"{C.MAX_STEPS} changes and no settling: tuning stopped there"})
        _enter_final(tour)
        return None
    knobs = [k for k in tour["knobs"] if k["id"] in tour["levels"]]
    live = [k for k in knobs if K.live_ok(k)]
    rest = [k for k in knobs if not K.live_ok(k)]
    v = tour["tune_verdict"]
    k, to, how = D.choose(live, tour["levels"], tour["ceilings"], v) if live else (None, "", "locked")
    if k is None and rest:
        k, to, how = D.choose(rest, tour["levels"], tour["ceilings"], v)
    if k is None:
        tour["changes"].append({"note": f"{how}: {to}"})
        _enter_final(tour)
        return None
    word = "lower" if how == "lower" else "raise"
    return {"do": "set", "knob": k["id"], "to": str(k["steps"][to]), "live": K.live_ok(k), "dir": how,
            "say": f"{word} {k['label']}: {K.shown(k, k['steps'][tour['levels'][k['id']]])} -> {K.shown(k, k['steps'][to])}"
                   + ("" if K.live_ok(k) else " (it needs a start: the game is restarted and the spot reached again)")}


# ---- what happened ---------------------------------------------------------------------------------------------
def arrived(game, label=None):
    tour = load(game)
    if label and tour["at"]:
        SP.name(game, tour["at"], label)
    if tour["at"]:
        _entry(tour, tour["at"])["god"] = False          # a fresh arrival: god mode is off again
    if not tour["live_read"]:
        for k in tour["knobs"]:
            if k.get("live"):
                i = K.step_index(k, K.live_value(k))
                if i is not None:
                    tour["levels"][k["id"]] = tour["start"][k["id"]] = i
        tour["live_read"] = True
    tour["need_restart"] = False
    tour["here"] = tour["at"]                          # where the game now stands
    tour["step"] = "settle"
    save(game, tour)


def settled(game):
    tour = load(game)
    tour["step"] = "god" if tour.get("godmode") and not _entry(tour, tour["at"])["god"] else "look"
    save(game, tour)


def godmode_on(game):
    tour = load(game)
    _entry(tour, tour["at"])["god"] = True
    tour["step"] = "look"
    save(game, tour)


def adjusted(tour, summary):
    """The summary with the connector's measured cost taken off the game's own work (nothing under the noise)."""
    ms = tour.get("connector_ms") or 0.0
    if not summary or ms <= 0:
        return summary
    s = dict(summary)
    s["work_p95_ms"] = round(max(0.0, s["work_p95_ms"] - ms), 6)
    s["connector_ms_subtracted"] = ms
    return s


def measured(game, rows, gpu):
    tour = load(game)
    sid = tour["at"]
    e = _entry(tour, sid)
    summary = adjusted(tour, R.summarize(rows, tour["target"]))
    v = D.verdict(summary, gpu)
    rec = {"summary": summary, "gpu": gpu, "verdict": v, "levels": dict(tour["levels"]),
           "when": time.strftime("%Y-%m-%d %H:%M:%S")}
    _marker(tour, sid, "measured")
    ph = tour["phase"]
    if ph == "tuning" and v["result"] == "short":
        tour["short_tries"] += 1
        if tour["short_tries"] > 1:
            tour["phase"], tour["stop_why"] = "stopped", "the tuning spot measured too briefly twice running"
        tour["step"] = "look"
        save(game, tour)
        return v
    tour["short_tries"] = 0
    e["last"] = rec
    if ph == "visiting":
        e["first"], e["status"] = rec, "done"
    elif ph == "final":
        tour["lap_done"].append(sid)
    elif ph == "tuning":
        _tuned_result(tour, v)
    tour["at"], tour["step"] = None, "reach"
    save(game, tour)
    return v


def _tuned_result(tour, v):
    pend, tour["pending"] = tour["pending"], None
    tour["tune_verdict"] = v
    if not pend:
        return
    tour["changes"][-1]["result"] = v["result"]
    if pend["dir"] == "raise" and v["result"] == "fails":
        tour["revert"] = {"knob": pend["knob"], "to": pend["from"]}
        tour["ceilings"][pend["knob"]] = pend["to"]
        tour["tune_verdict"] = {"result": "holds", "bound": None, "room": True}    # it held before the raise


def left(game):
    """The game was closed (quit_game): it stands nowhere now."""
    tour = load(game)
    tour["here"] = None
    save(game, tour)


def crashed(game):
    tour = load(game)
    tour["here"] = None
    e = _entry(tour, tour["at"])
    e["crashes"] += 1
    if e["crashes"] > C.SPOT_CRASH_RETRIES:
        e["status"] = "unreachable"
        _leave(tour, "could not be reached: the game crashed on the way there, twice")
    else:
        tour["step"], tour["need_restart"] = "reach", True
    save(game, tour)


def died(game):
    tour = load(game)
    tour["here"] = None
    e = _entry(tour, tour["at"])
    e["deaths"] += 1
    if e["deaths"] >= C.SPOT_DEATHS_UNSAFE:
        e["status"] = "unsafe"
        _leave(tour, "unsafe: the player died there twice")
    else:
        tour["step"], tour["need_restart"] = "reach", True
    save(game, tour)


def _leave(tour, why):
    sid = tour["at"]
    tour["spots"][sid]["why"] = why
    if tour["phase"] == "final":
        tour["lap_done"].append(sid)
    if tour["phase"] == "tuning" and sid == tour["tuning_spot"]:
        tour["phase"], tour["stop_why"] = "stopped", f"the tuning spot {why}"
    tour["at"], tour["step"] = None, "reach"


def changed(game, knob_id, to):
    """A setting was changed (live, or written for the next start). `to` is the step as named in next_step."""
    tour = load(game)
    k = _knobs(tour)[knob_id]
    i = K.step_index(k, to)
    frm = tour["levels"].get(knob_id)
    tour["levels"][knob_id] = i
    if tour["revert"] and tour["revert"]["knob"] == knob_id:
        tour["revert"] = None
        tour["changes"].append({"knob": knob_id, "from": frm, "to": i, "dir": "back"})
        if not K.live_ok(k):
            tour["need_restart"] = True
        save(game, tour)
        return
    tour["pending"] = {"knob": knob_id, "from": frm, "to": i, "dir": "raise" if i > frm else "lower"}
    tour["changes"].append({"knob": knob_id, "from": frm, "to": i, "dir": tour["pending"]["dir"]})
    tour["steps"] += 1
    tour["at"] = tour["tuning_spot"]
    if not K.live_ok(k) or tour["need_restart"] or tour.get("here") != tour["tuning_spot"]:
        tour["need_restart"], tour["step"] = True, "reach"     # the game is elsewhere (or must restart): go back there
    else:
        tour["step"] = "settle"
    save(game, tour)


def cost(game, with_ms, without_ms):
    """The connector's own cost at the tuning spot: under the noise nothing is subtracted."""
    tour = load(game)
    d = with_ms - without_ms
    if d < C.CONNECTOR_NOISE_MS:
        tour["connector_ms"] = 0.0
        tour["connector_say"] = f"the connector costs {d:.2f} ms a frame, under the noise ({C.CONNECTOR_NOISE_MS} ms): nothing subtracted"
    else:
        tour["connector_ms"] = round(d, 6)
        tour["connector_say"] = f"the connector costs {d:.2f} ms a frame: subtracted from every measure"
    with open(_cost_path(game), "w", encoding="utf-8") as f:
        json.dump({"build": tour["build"], "ms": tour["connector_ms"], "say": tour["connector_say"]}, f)
    if tour["phase"] == "cost":
        tour["phase"] = "tuning"
    save(game, tour)


def stop(game, why):
    tour = load(game)
    tour["phase"], tour["stop_why"] = "stopped", why
    save(game, tour)


# ---- ranking ---------------------------------------------------------------------------------------------------
def _measured(tour, ids=None):
    out = []
    for sid, e in tour["spots"].items():
        last = e.get("last")
        if (ids is None or sid in ids) and e["status"] == "done" and last and last["verdict"]["result"] != "short":
            out.append((sid, last))
    return out


def _key(last):
    return (last["summary"]["low1_fps"], -last["summary"]["late_pct"])


def _failing_card(tour, ids=None):
    f = [(sid, last) for sid, last in _measured(tour, ids)
         if last["verdict"]["result"] == "fails" and last["verdict"]["bound"] in ("card", None)]
    return [sid for sid, last in sorted(f, key=lambda x: _key(x[1]))]


def _is_cpu(tour, sid):
    last = tour["spots"].get(sid, {}).get("last")
    return bool(last) and last["verdict"]["result"] == "fails" and last["verdict"]["bound"] == "processor"


def rank(tour):
    """(the tuning spot, the processor-limited spots). The tuning spot is the worst failing spot the graphics card
    limits (slowest 1% first); when every spot holds, the worst holding one (to raise the picture there)."""
    failing = _failing_card(tour)
    cpu = sorted(sid for sid, _ in _measured(tour) if _is_cpu(tour, sid))
    if failing:
        return failing[0], cpu
    holding = sorted(((sid, last) for sid, last in _measured(tour) if last["verdict"]["result"] == "holds"),
                     key=lambda x: _key(x[1]))
    return (holding[0][0] if holding else None), cpu


def short_by_ms(tour, sid):
    last = tour["spots"][sid]["last"]
    s = last["summary"]
    return round(max(0.0, 1000.0 / max(s["low1_fps"], 0.1) - 1000.0 / s["target"]), 1)


def spot_words(tour, sid):
    e = tour["spots"].get(sid, {})
    label = e.get("label") or sid
    if e.get("status") in ("unreachable", "unsafe"):
        return f"{label}: {e.get('why', e['status'])}"
    last = e.get("last")
    if not last:
        return f"{label}: not measured"
    if _is_cpu(tour, sid):
        return (f"{label}: settings can't fix this (the processor is the limit), short by {short_by_ms(tour, sid)} ms "
                f"on its slowest frames")
    return f"{label}: {D.plain(last['summary'], last['gpu'], last['verdict'])}"


# ---- spot markers for the collector ----------------------------------------------------------------------------
def _marker(tour, sid, event):
    d = C.meter_dir()
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, f"{tour['stamp']}_{tour['exe_stem']}.frametime-spots.tsv")
    new = not os.path.isfile(path)
    settings = ",".join(f"{k}={_step(tour, k)}" for k in sorted(tour["levels"]))
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        if new:
            f.write("t_unix\tspot\tevent\tsettings\n")
        f.write(f"{time.time():.3f}\t{sid}\t{event}\t{settings}\n")


def _step(tour, kid):
    return _knobs(tour)[kid]["steps"][tour["levels"][kid]]


def marker(game, event):
    """A line in the spot-marker file beside the meter's recording (the collector shelves both)."""
    tour = load(game)
    _marker(tour, tour.get("at") or "-", event)
