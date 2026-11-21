"""finish.py - the end of a tour: write every setting to where the game keeps it (apply), check after the next start
that the game did not throw them away (check_applied), the result in plain words (result, also result.txt), and undo.

Apply runs only with the game closed: a running game can write its own settings file over ours when it quits (Silent
Hill 2 does). A setting that lives only while the game runs (keep: null) is never counted as applied: the result says
it holds only while it is re-applied.
"""
import os
import time

from engine import knobs as K
from engine import read as R
from engine import settings as C
from engine import tour as T

LOOKS = {0: "nothing you can see", 1: "a little", 2: "some", 3: "a lot"}


def _kept(k):
    """The knob as written to its lasting home."""
    kc = dict(k)
    kc["file"] = k["keep"]
    if kc["kind"] == "live_cvar":
        kc["kind"] = "console_script"
    return kc


def _value(k, i):
    return K.shown(k, k["steps"][i])


def apply(game):
    tour = T.load(game)
    if C.game_running(tour["exe"]):
        return ["the game is still running: close it by its own quit first, then apply "
                "(it could write its own settings over ours as it quits)"]
    lines, applied = [], {}
    for k in tour["knobs"]:
        i = tour["levels"].get(k["id"])
        if i is None:
            lines.append(f"{k['label']}: not known, left as it is")
            continue
        val = str(k["steps"][i])
        if k.get("keep") is None:
            lines.append(f"{k['label']}: {_value(k, i)} holds only while you re-apply it (the game forgets it at its "
                         f"next start)")
            continue
        if i == tour["start"].get(k["id"]):
            lines.append(f"{k['label']}: {_value(k, i)} (unchanged)")
            continue
        K.set_value(_kept(k), val, {"exe": tour["exe"]}, game)
        applied[k["id"]] = val
        lines.append(f"{k['label']}: {_value(k, i)} (written to where the game keeps it)")
    tour["applied"] = applied
    tour["apply_lines"] = lines
    tour["phase"] = "done"
    T.save(game, tour)
    return lines


def check_applied(game):
    """After the game's next start: every applied setting read back. A setting the game put back 'did not stick'."""
    tour = T.load(game)
    knobs = {k["id"]: k for k in tour["knobs"]}
    lines = []
    for kid, val in (tour.get("applied") or {}).items():
        k = knobs[kid]
        now = K.get_value(_kept(k), {"exe": tour["exe"]})
        if K.step_index(k, now) != K.step_index(k, val):
            lines.append(f"{k['label']} did not stick: the game put it back to {K.shown(k, now)} at its start")
        else:
            lines.append(f"{k['label']}: stuck at {K.shown(k, val)}")
    tour["check_lines"] = lines
    T.save(game, tour)
    return lines


def _rank_key(tour, sid):
    last = tour["spots"][sid].get("last")
    if not last:
        return (float("inf"), 0)
    return (last["summary"]["low1_fps"], -last["summary"]["late_pct"])


def result(game):
    tour = T.load(game)
    lines = [f"The Optimizer: {tour['pack']}, {time.strftime('%Y-%m-%d %H:%M')}",
             f"Target: {tour['target']:g} frames a second. Finished in phase: {tour['phase']}"
             + (f" ({tour['stop_why']})" if tour.get("stop_why") else ""), ""]
    measured = [sid for sid, e in tour["spots"].items() if e.get("last") and e["status"] == "done"]
    lines.append("The spots, worst first:")
    for n, sid in enumerate(sorted(measured, key=lambda s: _rank_key(tour, s)), 1):
        mark = "  (the tuning spot)" if sid == tour.get("tuning_spot") else ""
        lines.append(f"  {n}. {T.spot_words(tour, sid)}{mark}")
    lines.append("")
    lines.append("The settings (start -> now), and what each costs in looks:")
    for k in tour["knobs"]:
        i, s = tour["levels"].get(k["id"]), tour["start"].get(k["id"])
        if i is None:
            continue
        move = f"{_value(k, s)} -> {_value(k, i)}" if s is not None and s != i else f"{_value(k, i)} (unchanged)"
        lines.append(f"  {k['label']}: {move}; costs in looks: {LOOKS.get(int(k.get('shows', 0)), '?')}")
    for ln in tour.get("apply_lines") or []:
        if "holds only while" in ln:
            lines.append(f"  ! {ln}")
    for ln in tour.get("check_lines") or []:
        if "did not stick" in ln:
            lines.append(f"  ! {ln}")
    cpu = [sid for sid in tour.get("processor") or [] if tour["spots"].get(sid, {}).get("last")]
    if cpu:
        lines += ["", "The processor is the limit here, so settings can't fix these:"]
        for sid in cpu:
            label = tour["spots"][sid].get("label") or sid
            lines.append(f"  {label}: short by {T.short_by_ms(tour, sid)} ms on its slowest frames")
    lost = [(sid, e) for sid, e in tour["spots"].items() if e["status"] in ("unreachable", "unsafe")]
    if lost:
        lines += ["", "Not measured:"]
        lines += [f"  {T.spot_words(tour, sid)}" for sid, _ in lost]
    any_gpu = any((e.get("last") or {}).get("gpu") for e in tour["spots"].values())
    lines += ["", "Measured with:",
              "  the frame meter (every frame the game handed to the headset)",
              "  " + ("the graphics card's load (nvidia-smi)" if any_gpu else
                      "no graphics-card numbers (nvidia-smi was not here): a card limit could not be told from a "
                      "processor one"),
              "  " + ("the real headset, worn" if tour.get("headset") else
                      "the pretend headset (OpenXR Simulator): its frame rate is close to, not the same as, a real "
                      "headset's"),
              "  " + (tour.get("connector_say") or "the connector's own cost was not measured")]
    os.makedirs(C.game_dir(game), exist_ok=True)
    with open(os.path.join(C.game_dir(game), "result.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return lines


def undo(game):
    """Every file The Optimizer changed for this game put back as it was. Nothing is sent live while the game runs."""
    tour = T.load(game)
    lines = K.restore_all(game) or ["no file had been changed"]
    if C.game_running(tour["exe"]):
        lines.append("the game is running: nothing was sent to it live; restart the game so it starts from the "
                     "settings put back")
    else:
        for k in tour["knobs"]:
            if K.live_ok(k) and k["id"] in tour["start"]:
                K.push_live(k, k["steps"][tour["start"][k["id"]]])
    tour["levels"] = dict(tour["start"])
    tour["phase"], tour["applied"] = "undone", {}
    T.save(game, tour)
    return lines


def summary_rows(rows, target):
    """One measure's numbers (used by the toolbox when it reports a look)."""
    return R.summarize(rows, target)
