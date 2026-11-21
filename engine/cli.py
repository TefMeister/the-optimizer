#!/usr/bin/env python3
"""cli.py - The Optimizer's tuning engine by hand: finds the best-looking settings a VR game can run at without
dropping under 72 frames a second. The window and the AI's toolbox call the same code; this is the plain way in.

Tefa, 2026-11-21: "can we make a tool that lets people fire up any game in VR and the tool will find the most optimal
setup for performance and graphics, so that the graphics never go lower than 72fps". Moved from Lanes' Tune-o-matiC
the same day, without the part that changed settings while playing (Tefa: "please remove for now").

    python -m engine.cli readers                     the measuring programs: which are on this PC, how to get the others
    python -m engine.cli profiles                    the game profiles (which settings each knows, how it reads them)
    python -m engine.cli meter build|status          build the frame meter (Visual Studio Build Tools), or how it stands
    python -m engine.cli meter on <game program>     install the meter and switch it on for that game only
    python -m engine.cli meter off [<game program>]  switch it off for that game (no game: every game, and unregister)
    python -m engine.cli start <game> --exe <program> [--profile <name>] [--target 72] [--asked <knob>=<step> ...]
                                                     begin tuning: reads every setting as it is now
    python -m engine.cli measure <game> [--seconds 60] [--csv <file>] [--flat]
                                                     judge the last N seconds of play (run it WHILE the game is played);
                                                     --flat reads a flat game through PresentMon instead of the meter
    python -m engine.cli next <game>                 make the ONE next change (or say the tuning is done)
    python -m engine.cli set <game> <knob> <step>    record a setting changed by hand in the game's own menu
    python -m engine.cli status <game>               every setting now and at the start, the last verdict
    python -m engine.cli undo <game>                 every changed file back as it was before the first change

THE LOOP: start -> (play, measure, next) until "locked". Launching and closing the game is the toolbox's job.
"""
import filecmp
import os
import shutil
import struct
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if os.path.dirname(HERE) not in sys.path:
    sys.path.insert(0, os.path.dirname(HERE))

from engine import settings as C  # noqa: E402
from engine import decide as D  # noqa: E402
from engine import knobs as K  # noqa: E402
from engine import read as R  # noqa: E402


def utf8_console():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

REG_KEY = r"Software\Khronos\OpenXR\1\ApiLayers\Implicit"
LAYER_FILES = ("lanes_tune_meter.dll", "lanes_tune_meter.json")
PE_OFFSET_AT = 0x3c
MACHINE_64 = 0x8664
WAIT_FOR_CSV_S = 5


def arg(argv, name, default=None):
    if name in argv:
        i = argv.index(name)
        if i + 1 < len(argv):
            return argv[i + 1]
    return default


def args_many(argv, name):
    return [argv[i + 1] for i, a in enumerate(argv) if a == name and i + 1 < len(argv)]


# ---- readers, profiles -----------------------------------------------------------------------------------------
def cmd_readers():
    for r in R.readers():
        mark = {True: "here   ", False: "missing", None: "extra  "}[r["here"]]
        C.say(f"{mark} {r['name']}: {r['what']}", f"        get: {r['get']}")
    return 0


def cmd_profiles():
    for name in C.profile_names():
        p = C.load_profile(name)
        C.say(f"{name}: {p['label']}")
        for k in p["knobs"]:
            live = ", changes live" if k.get("live") else ""
            C.say(f"   {k['id']}: {k['label']} ({len(k['steps'])} steps, shows {k['shows']}/3, costs {k['cost']}/3{live})")
    return 0


# ---- the meter -------------------------------------------------------------------------------------------------
def _fake_reg():
    return os.environ.get("OPTIMIZER_FAKEREG")


def _reg(action, name):
    """Our own registry value only: never anyone else's layer."""
    fake = _fake_reg()
    if fake:
        import json
        vals = {}
        if os.path.isfile(fake):
            with open(fake, encoding="utf-8") as f:
                vals = json.load(f)
        if action == "set":
            vals[name] = 0
        elif action == "del":
            vals.pop(name, None)
        with open(fake, "w", encoding="utf-8") as f:
            json.dump(vals, f)
        return name in vals
    import winreg
    if action == "set":
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_KEY) as k:
            winreg.SetValueEx(k, name, 0, winreg.REG_DWORD, 0)
        return True
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_ALL_ACCESS) as k:
            if action == "del":
                winreg.DeleteValue(k, name)
                return False
            winreg.QueryValueEx(k, name)
            return True
    except OSError:
        return False


def _is_64(exe):
    try:
        with open(exe, "rb") as f:
            f.seek(PE_OFFSET_AT)
            pe = struct.unpack("<I", f.read(4))[0]
            f.seek(pe + 4)
            return struct.unpack("<H", f.read(2))[0] == MACHINE_64
    except (OSError, struct.error):
        return None


def _meter_settings():
    path = os.path.join(C.layer_dir(), "lanes_tune_meter.txt")
    exes = []
    try:
        for line in open(path, encoding="utf-8"):
            k, _, v = line.partition("=")
            if k.strip().lower() == "exe":
                exes = [e.strip() for e in v.split(",") if e.strip()]
    except OSError:
        pass
    return path, exes


def _write_meter_settings(exes):
    path, _ = _meter_settings()
    os.makedirs(C.layer_dir(), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("# The Optimizer's frame meter: which games it measures and where it writes "
                "(python -m engine.cli meter on/off writes this file)\n")
        f.write(f"on = {1 if exes else 0}\nexe = {', '.join(exes)}\nout = {C.meter_dir()}\n")


def cmd_meter(argv):
    sub = argv[0] if argv else "status"
    manifest = os.path.join(C.layer_dir(), "lanes_tune_meter.json")
    if sub == "build":
        if os.name != "nt":
            C.say("the meter is built on Windows only")
            return 1
        return subprocess.call(["cmd", "/c", os.path.join(C.METER_SRC, "build.bat")])
    if sub == "status":
        _, exes = _meter_settings()
        reg = _reg("get", manifest)
        C.say(f"frame meter: {'registered' if reg else 'not registered'}; measuring: {', '.join(exes) or 'no game'}",
              f"its files: {C.meter_dir()}")
        return 0
    if sub == "on":
        if len(argv) < 2:
            C.say("usage: python -m engine.cli meter on <the game's program>")
            return 2
        exe = argv[1]
        if _is_64(exe) is False:
            C.say("this game is 32-bit; the meter is 64-bit only for now (a 64-bit layer listed for a 32-bit game "
                  "once stopped a game from starting, so it is not registered)")
            return 1
        dist = os.environ.get("OPTIMIZER_METER_DIST") or os.path.join(C.METER_SRC, "dist")
        if not all(os.path.isfile(os.path.join(dist, f)) for f in LAYER_FILES):
            C.say("the meter is not built yet: python -m engine.cli meter build")
            return 1
        os.makedirs(C.layer_dir(), exist_ok=True)
        for f in LAYER_FILES:
            src, dst = os.path.join(dist, f), os.path.join(C.layer_dir(), f)
            try:
                if not os.path.isfile(dst) or not filecmp.cmp(src, dst, shallow=False):
                    shutil.copy2(src, dst)
            except PermissionError:
                C.say(f"{f} is in use (a game has the meter loaded): close the game, then run this again")
                return 1
        _, exes = _meter_settings()
        name = os.path.basename(exe)
        if name.lower() not in [e.lower() for e in exes]:
            exes.append(name)
        _write_meter_settings(exes)
        _reg("set", manifest)
        C.say(f"frame meter on for {name} (it starts measuring with the game's next VR start); "
              f"to switch it off for the game alone: set the environment value DISABLE_OPTIMIZER_METER=1")
        return 0
    if sub == "off":
        _, exes = _meter_settings()
        if len(argv) > 1:
            name = os.path.basename(argv[1]).lower()
            exes = [e for e in exes if e.lower() != name]
        else:
            exes = []
        _write_meter_settings(exes)
        if not exes:
            _reg("del", manifest)
        C.say(f"frame meter now measures: {', '.join(exes) or 'no game (unregistered)'}")
        return 0
    C.say("usage: python -m engine.cli meter build|status|on <program>|off [<program>]")
    return 2


# ---- one game's tuning -----------------------------------------------------------------------------------------
def _active_runtime():
    if os.environ.get("OPTIMIZER_RUNTIME") is not None:
        return os.environ["OPTIMIZER_RUNTIME"].lower()
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Khronos\OpenXR\1") as k:
            return str(winreg.QueryValueEx(k, "ActiveRuntime")[0]).lower()
    except (ImportError, OSError):
        return ""


def guess_profile(exe):
    low = exe.lower().replace("/", "\\")
    if os.path.basename(low) == "cemu.exe" and os.path.isdir(os.path.join(os.path.dirname(exe), "BetterVR")):
        return "botw-bettervr"
    if low.endswith("-shipping.exe") or "\\binaries\\win64\\" in low:
        return "unreal-uevr"
    return "generic-vr"


def knobs_for(state):
    p = C.load_profile(state["profile"])
    rt = _active_runtime()
    out = []
    for k in p["knobs"]:
        need = (k.get("when") or {}).get("runtime")
        if need and need.lower() not in rt:
            continue
        out.append(k)
    return out


def game_of(state):
    return {"exe": state["exe"], "asked": state.get("asked", {}), "paths": state.get("paths", {})}


FROM = {"live": "(read live)", "file": "(from the game's settings file)", "default": "(not set: the game's default)"}


def cmd_start(argv):
    if not argv or argv[0].startswith("--"):
        C.say("usage: python -m engine.cli start <game> --exe <program> [--profile <name>] [--target 72]")
        return 2
    game, exe = argv[0], arg(argv, "--exe")
    if not exe:
        C.say("python -m engine.cli start needs --exe <the game's program> (the meter and the profiles find things from it)")
        return 2
    profile = arg(argv, "--profile") or guess_profile(exe)
    target = float(arg(argv, "--target", C.DEFAULT_TARGET_FPS))
    state = {"game": C.slug(game), "exe": os.path.abspath(exe), "profile": profile, "target": target,
             "levels": {}, "start": {}, "ceilings": {}, "asked": {}, "phase": "tuning", "pending": None, "steps": 0}
    for a in args_many(argv, "--asked"):
        k, _, v = a.partition("=")
        state["asked"][k.strip()] = v.strip()
    lines = [f"tuning {state['game']} with the '{profile}' profile, target {target:g} frames a second"]
    for k in knobs_for(state):
        val, src = K.start_value(k, game_of(state))
        i = K.step_index(k, val)
        if i is None:
            lines.append(f"   {k['label']}: not known yet ({val!r}): python -m engine.cli set {state['game']} {k['id']} <step>")
            continue
        state["levels"][k["id"]] = state["start"][k["id"]] = i
        lines.append(f"   {k['label']}: {K.shown(k, k['steps'][i])} {FROM[src]}")
    C.note(state, "started")
    C.save_state(state)
    C.say(*lines, "next: play a busy stretch of the game and run, while playing: "
                  f"python -m engine.cli measure {state['game']} --seconds 60")
    return 0


def _measure_rows(state, argv, seconds):
    csv_path = arg(argv, "--csv")
    if csv_path:
        rows = R.read_meter_csv(csv_path)
        return (R.last_seconds(rows, seconds) if "--seconds" in argv else rows), None, None
    stem = os.path.splitext(os.path.basename(state["exe"]))[0]
    sampler = R.GpuSampler().start()
    if "--flat" in argv:
        rows, why = R.presentmon_rows(os.path.basename(state["exe"]), seconds)
        return rows or [], sampler.stop(), why
    t0 = time.time()
    time.sleep(seconds)
    gpu = sampler.stop()
    for _ in range(WAIT_FOR_CSV_S):
        files = [f for f in R.meter_csvs(stem) if os.path.getmtime(f) >= t0]
        if files:
            return R.last_seconds(R.read_meter_csv(files[-1]), seconds), gpu, None
        time.sleep(1)
    return [], gpu, (f"the frame meter wrote nothing for {stem} during those {seconds:g} s: is the game in VR, and is "
                     f"the meter on for it (python -m engine.cli meter status)?")


def cmd_measure(argv):
    state = C.load_state(argv[0])
    seconds = float(arg(argv, "--seconds", 60))
    rows, gpu, why = _measure_rows(state, argv, seconds)
    if why:
        C.say(why)
    if gpu is None and "--csv" not in argv and not why:
        C.say("(no graphics-card numbers: nvidia-smi is not here, so a card limit cannot be told from a processor one)")
    summary = R.summarize(rows, state["target"])
    v = D.verdict(summary, gpu)
    state["last"] = {"summary": summary, "gpu": gpu, "verdict": v, "when": time.strftime("%Y-%m-%d %H:%M:%S")}
    C.say(D.plain(summary, gpu, v))
    pend = state.get("pending")
    if pend and v["result"] != "short":
        knobs = {k["id"]: k for k in knobs_for(state)}
        k = knobs.get(pend["knob"])
        if pend["dir"] == "raise" and v["result"] == "fails" and k:
            K.set_value(k, k["steps"][pend["from"]], game_of(state), state["game"])
            state["levels"][k["id"]] = pend["from"]
            state["ceilings"][k["id"]] = pend["to"]
            C.say(f"the raise of {k['label']} to {k['steps'][pend['to']]} did not hold: put back to "
                  f"{k['steps'][pend['from']]} and remembered as its ceiling" +
                  ("; restart the game before the next test" if k.get("restart", True) else ""))
            C.note(state, f"raise of {k['id']} failed; back to {pend['from']}")
            state["last"]["verdict"] = {"result": "holds", "bound": None, "room": True}   # it held before the raise
        else:
            C.note(state, f"{pend['dir']} of {pend['knob']}: {v['result']}")
        state["pending"] = None
    C.save_state(state)
    if state["phase"] == "tuning":
        C.say(f"next: python -m engine.cli next {state['game']}")
    return 0


def cmd_next(argv):
    state = C.load_state(argv[0])
    if state.get("pending"):
        C.say(f"the last change ({state['pending']['knob']}) has not been measured yet: python -m engine.cli measure {state['game']}")
        return 1
    if state["phase"] != "tuning":
        C.say(f"tuning is {state['phase']}: python -m engine.cli status {state['game']}")
        return 0
    if "last" not in state:
        C.say(f"nothing measured yet: python -m engine.cli measure {state['game']}")
        return 1
    if state["steps"] >= C.MAX_STEPS:
        state["phase"] = "stopped"
        C.save_state(state)
        C.say(f"{C.MAX_STEPS} changes and no settling: stopped; python -m engine.cli status {state['game']} shows where it stands")
        return 1
    knobs = knobs_for(state)
    k, to, how = D.choose(knobs, state["levels"], state["ceilings"], state["last"]["verdict"])
    if k is None:
        if how == "short":
            C.say(to)
            return 1
        state["phase"] = how
        if how == "locked":
            state["tuned"] = dict(state["levels"])
        C.note(state, f"{how}: {to}")
        C.save_state(state)
        C.say(f"{'DONE' if how == 'locked' else 'STOPPED'}: {to}")
        return cmd_status([state["game"]])
    frm = state["levels"][k["id"]]
    _, ask = K.set_value(k, k["steps"][to], game_of(state), state["game"])
    live_ok = False
    if k.get("live") and C.game_running(state["exe"]):
        live_ok, said = K.push_live(k, k["steps"][to])
        if not live_ok:
            C.say(f"(not changed live: {said})")
    state["levels"][k["id"]] = to
    state["pending"] = {"knob": k["id"], "from": frm, "to": to, "dir": how}
    state["steps"] += 1
    C.note(state, f"{how} {k['id']}: {k['steps'][frm]} -> {k['steps'][to]}")
    C.save_state(state)
    C.say(f"{'lowered' if how == 'lower' else 'raised'} {k['label']}: {k['steps'][frm]} -> {k['steps'][to]}")
    if ask:
        C.say(f"BY HAND: {ask}")
    elif not live_ok:
        C.say("restart the game so it reads the change, then play and measure again")
    else:
        C.say("changed in the running game: play on and measure again")
    C.say(f"then: python -m engine.cli measure {state['game']} --seconds 60")
    return 0


def cmd_set(argv):
    if len(argv) < 3:
        C.say("usage: python -m engine.cli set <game> <knob> <step>")
        return 2
    state = C.load_state(argv[0])
    knobs = {k["id"]: k for k in knobs_for(state)}
    k = knobs.get(argv[1])
    if not k:
        C.say(f"no setting '{argv[1]}' in this profile: {', '.join(knobs)}")
        return 2
    i = K.step_index(k, argv[2])
    if i is None:
        C.say(f"'{argv[2]}' is not one of its steps: {', '.join(map(str, k['steps']))}")
        return 2
    state.setdefault("asked", {})[k["id"]] = str(k["steps"][i])
    state["levels"][k["id"]] = i
    state["start"].setdefault(k["id"], i)
    C.note(state, f"set by hand: {k['id']} = {k['steps'][i]}")
    C.save_state(state)
    C.say(f"{k['label']}: recorded as {k['steps'][i]}")
    return 0


def cmd_status(argv):
    state = C.load_state(argv[0])
    C.say(f"{state['game']}: {state['phase']}, profile {state['profile']}, target {state['target']:g}, "
          f"{state['steps']} change(s)")
    for k in knobs_for(state):
        i, s = state["levels"].get(k["id"]), state["start"].get(k["id"])
        if i is None:
            C.say(f"   {k['label']}: not known")
            continue
        extra = f" (was {k['steps'][s]})" if s is not None and s != i else ""
        if k["id"] in state["ceilings"]:
            extra += f", failed at {k['steps'][state['ceilings'][k['id']]]}"
        C.say(f"   {k['label']}: {k['steps'][i]}{extra}")
    last = state.get("last")
    if last:
        C.say(f"last test ({last['when']}): {D.plain(last['summary'], last['gpu'], last['verdict'])}")
    return 0


def cmd_undo(argv):
    state = C.load_state(argv[0])
    lines = K.restore_all(state["game"])
    running = C.game_running(state["exe"])
    if running:
        lines.append("the game is running: nothing was sent to it live; restart the game so it starts from the "
                     "settings put back")
    else:
        for k in knobs_for(state):
            if K.live_ok(k) and k["id"] in state["start"]:
                K.push_live(k, k["steps"][state["start"][k["id"]]])
    state["levels"] = dict(state["start"])
    state["phase"], state["pending"] = "undone", None
    C.note(state, "undone")
    C.save_state(state)
    C.say(*(lines or ["no file had been changed"]))
    asked = [k for k in knobs_for(state) if k["kind"] == "ask" and k["id"] in state["start"]]
    for k in asked:
        C.say(f"BY HAND: put {k['label']} back to {k['steps'][state['start'][k['id']]]} in {k.get('where', 'the game')}")
    return 0


def main(argv):
    utf8_console()
    if not argv or argv[0] in ("-h", "--help", "help"):
        C.say(__doc__.strip())
        return 0
    cmd, rest = argv[0], argv[1:]
    simple = {"readers": cmd_readers, "profiles": cmd_profiles}
    if cmd in simple:
        return simple[cmd]()
    if cmd == "meter":
        return cmd_meter(rest)
    per_game = {"start": cmd_start, "measure": cmd_measure, "next": cmd_next, "set": cmd_set, "status": cmd_status,
                "undo": cmd_undo}
    if cmd in per_game:
        if not rest:
            C.say(f"usage: python -m engine.cli {cmd} <game> ...")
            return 2
        return per_game[cmd](rest)
    C.say(f"optimizer: no command '{cmd}' (python -m engine.cli help)")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
