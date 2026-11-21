"""decide.py - The Optimizer's judgement, with no files and no games in it (so the tests can drive it).

A test HOLDS when at most HOLD_MISSED_PCT of its frames were late and its slowest 1% still ran at HOLD_LOW_SHARE of
the target. Then:
  failing        lower ONE setting one step. Which: the one that shows least for what it costs (a setting that shows
                 nothing goes first: "invisible savings first", Tefa's Silent Hill 2 rule). When the graphics card was
                 NOT the limit, only settings marked "cpu" help; with none left, the tool says so instead of
                 blurring the picture for nothing.
  holding, room  raise ONE setting one step: the one that shows most for what it costs, never past a step that has
                 already failed (its "ceiling").
  holding, full  done: these are the settings ("locked").
A raise that fails is put back at once and remembered as that setting's ceiling. One change per test, so every test
says what that one change did.
"""
from engine import settings as C


def verdict(summary, gpu):
    """'holds' / 'fails' / 'short', the limit when failing ('card' / 'processor' / None), and room when holding."""
    if not summary or summary["frames"] < C.MIN_FRAMES:
        return {"result": "short", "bound": None, "room": False}
    holds = summary["late_pct"] <= C.HOLD_MISSED_PCT and summary["low1_fps"] >= C.HOLD_LOW_SHARE * summary["target"]
    load = gpu.get("load_avg") if gpu else None
    if holds:
        if load is not None:
            room = load < C.ROOM_GPU_PCT
        else:
            room = summary["work_p95_ms"] < C.ROOM_WORK_SHARE * summary["frame_ms"]
        return {"result": "holds", "bound": None, "room": room}
    bound = None if load is None else ("card" if load >= C.GPU_BOUND_PCT else "processor")
    return {"result": "fails", "bound": bound, "room": False}


def _ratio_low(k):
    """lowering order: shows least per cost first (0 shows = free to lower)."""
    return (k["shows"] / max(k["cost"], 1), -k["cost"])


def _ratio_high(k):
    """raising order: shows most per cost first."""
    return (-(k["shows"] / max(k["cost"], 1)), k["cost"])


def choose(knobs, levels, ceilings, v, avoid=None):
    """The next change: (knob, new_step, 'lower'|'raise') or (None, reason, 'locked'|'stuck'|'processor')."""
    if v["result"] == "fails":
        cands = [k for k in knobs if levels.get(k["id"]) is not None and levels[k["id"]] > int(k.get("floor", 0))]
        if v["bound"] == "processor":
            cpu = [k for k in cands if k.get("cpu")]
            if not cpu:
                return None, ("the processor is the limit, not the graphics card: no setting left in this profile "
                              "lightens the processor's work, so lowering the picture would not help"), "processor"
            cands = cpu
        if not cands:
            return None, "every setting is at its lowest allowed step and it still does not hold the target", "stuck"
        k = sorted(cands, key=_ratio_low)[0]
        return k, levels[k["id"]] - 1, "lower"
    if v["result"] == "holds" and v["room"]:
        cands = []
        for k in knobs:
            i = levels.get(k["id"])
            if i is None or i + 1 >= len(k["steps"]) or k["id"] == avoid:
                continue
            if k["id"] in ceilings and i + 1 >= ceilings[k["id"]]:
                continue
            cands.append(k)
        if cands:
            k = sorted(cands, key=_ratio_high)[0]
            return k, levels[k["id"]] + 1, "raise"
        return None, "it holds the target and every setting is as high as it goes (or as high as held before)", "locked"
    if v["result"] == "holds":
        return None, "it holds the target with no room to spare: these are the settings", "locked"
    return None, "the test was too short to judge: measure again for longer", "short"


def plain(summary, gpu, v):
    """One line a person can read."""
    if not summary:
        return "no frames were measured"
    s = (f"{summary['fps']} frames a second on average, the slowest 1% at {summary['low1_fps']}; "
         f"{summary['late_pct']}% late against {summary['target']:g} ({summary['late']} of {summary['frames']})")
    if gpu and gpu.get("load_avg") is not None:
        s += f"; graphics card {gpu['load_avg']:g}% busy, up to {gpu.get('temp_max', '?'):g} C"
    word = {"holds": "HOLDS", "fails": "DOES NOT HOLD", "short": "TOO SHORT"}[v["result"]]
    tail = ""
    if v["result"] == "fails" and v["bound"]:
        tail = f" (the {'graphics card' if v['bound'] == 'card' else 'processor'} is the limit)"
    if v["result"] == "holds":
        tail = " with room to spare" if v["room"] else " with no room to spare"
    return f"{word}{tail}: {s}"
