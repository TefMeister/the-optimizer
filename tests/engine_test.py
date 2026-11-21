"""engine_test.py - The Optimizer's tuning engine (moved from Tune-o-matiC) with a pretend Unreal game, a pretend UEVR
connector and made-up frame-meter recordings: the whole tune-once loop, the backups and undo, the meter switch.
Nothing of a real game, no registry (a fake one), everything in a temp folder. Exit 0 = pass."""
import contextlib
import io
import json
import os
import struct
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
fails = 0
SENT = []


def check(ok, what):
    global fails
    print(("  ok    " if ok else "FAIL: ") + what)
    fails += not ok


class Fake(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        SENT.append(json.loads(self.rfile.read(n))["command"])
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

    def log_message(self, *a):
        pass


def make_csv(path, frames, late_every=0, work=4.0, period=13.889):
    with open(path, "w", encoding="utf-8") as f:
        f.write("# test\nt_ms,interval_ms,wait_ms,work_ms,period_ms,missed\n")
        t = 0.0
        for i in range(frames):
            iv = period * 2 if late_every and i % late_every == 0 else period
            t += iv
            f.write(f"{t:.3f},{iv:.3f},2.0,{work:.3f},{period:.3f},{int(iv > 1.5 * period)}\n")
    return path


def run(tune, *argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = tune.main(list(argv))
    return code, out.getvalue()


def main():
    t = tempfile.mkdtemp(prefix="tune-test-")
    os.environ["OPTIMIZER_DIR"] = os.path.join(t, "optimizer")
    os.environ["OPTIMIZER_LANES_CONF"] = os.path.join(t, "lanes.conf")
    os.environ["OPTIMIZER_RUNTIME"] = "virtualdesktop"
    os.environ["OPTIMIZER_NO_GPU"] = "1"
    os.environ["OPTIMIZER_FAKEREG"] = os.path.join(t, "reg.json")
    os.environ["APPDATA"] = os.path.join(t, "appdata")
    srv = HTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    os.environ["OPTIMIZER_UEVR_BASE"] = f"http://127.0.0.1:{srv.server_port}"
    os.environ["OPTIMIZER_FAKE_RUNNING"] = "1"      # the pretend game counts as running: safe settings go live
    from engine import cli as tune
    from engine import settings as C
    from engine import decide as D
    from engine import knobs as K
    from engine import read as R

    # every shipped profile loads and passes its own check
    for name in C.profile_names():
        try:
            C.load_profile(name)
            check(True, f"profile {name} loads")
        except SystemExit as e:
            check(False, f"profile {name}: {e}")
    check({"generic-vr", "unreal-uevr", "botw-bettervr"} <= set(C.profile_names()), "the three first profiles ship")

    # the numbers from a recording
    smooth = R.summarize(R.read_meter_csv(make_csv(os.path.join(t, "s.csv"), 720)), 72)
    check(smooth["late_pct"] == 0 and abs(smooth["fps"] - 72) < 0.5 and smooth["hz"] == 72.0, "a smooth 72 Hz test")
    check(D.verdict(smooth, None) == {"result": "holds", "bound": None, "room": True}, "smooth + light work: holds, room")
    heavy = R.summarize(R.read_meter_csv(make_csv(os.path.join(t, "h.csv"), 720, late_every=10)), 72)
    check(heavy["late_pct"] == 10.0 and D.verdict(heavy, None)["result"] == "fails", "one frame in ten late: fails")
    check(D.verdict(heavy, {"load_avg": 97})["bound"] == "card", "failing with the card at 97%: the card is the limit")
    check(D.verdict(heavy, {"load_avg": 55})["bound"] == "processor", "failing with the card at 55%: the processor")
    check(D.verdict(R.summarize(R.read_meter_csv(make_csv(os.path.join(t, "x.csv"), 100)), 72), None)["result"]
          == "short", "100 frames is too short to judge")
    full = R.summarize(R.read_meter_csv(make_csv(os.path.join(t, "f.csv"), 720, work=12.0)), 72)
    check(D.verdict(full, None)["room"] is False, "holding with 12 ms of work in a 13.9 ms frame: no room")

    # a pretend Unreal game in UEVR
    exe = os.path.join(t, "Game", "Binaries", "Win64", "Pretend-Win64-Shipping.exe")
    os.makedirs(os.path.dirname(exe))
    with open(exe, "wb") as f:   # just enough of a 64-bit program's header for the bitness check
        f.write(b"MZ" + b"\0" * 58 + struct.pack("<I", 64) + b"PE\0\0" + struct.pack("<H", 0x8664) + b"\0" * 32)
    prof_dir = os.path.join(t, "appdata", "UnrealVRMod", "Pretend-Win64-Shipping")
    os.makedirs(prof_dir)
    script = os.path.join(prof_dir, "user_script.txt")
    check(tune.guess_profile(exe) == "unreal-uevr", "an Unreal -Shipping program gets the Unreal profile")
    code, out = run(tune, "start", "Pretend Game", "--exe", exe)
    check(code == 0 and "Shadows: 3" in out, "start reads every setting (absent lines: the engine's default)")

    code, out = run(tune, "measure", "pretend-game", "--csv", os.path.join(t, "h.csv"))
    check("DOES NOT HOLD" in out, "the heavy test does not hold")
    code, out = run(tune, "next", "pretend-game")
    check("lowered Post-processing: 3 -> 2" in out, "first change: what shows least for its cost (post-processing)")
    check(open(script).read().strip() == "sg.PostProcessQuality 2", "written to UEVR's start-up script")
    check(SENT[-1:] == ["sg.PostProcessQuality 2"], "and sent live to the running game")
    code, out = run(tune, "next", "pretend-game")
    check(code == 1 and "not been measured" in out, "one change per test: next refuses before a measure")

    run(tune, "measure", "pretend-game", "--csv", os.path.join(t, "s.csv"))
    code, out = run(tune, "next", "pretend-game")
    check("raised Picture sharpness (render resolution, %): 100 -> 110" in out,
          "holding with room: first up is what shows most for its cost (the sharpness)")
    check("restart the game so it reads the change" in out,
          "the sharpness is not safe to change live: it waits for a restart, and says so")
    code, out = run(tune, "measure", "pretend-game", "--csv", os.path.join(t, "h.csv"))
    check("did not hold: put back to 100" in out and "r.ScreenPercentage 100" in open(script).read(),
          "a raise that fails is put back at once")
    code, out = run(tune, "next", "pretend-game")
    check("raised Post-processing: 2 -> 3" in out, "then the next one up (the sharpness is at its ceiling)")
    run(tune, "measure", "pretend-game", "--csv", os.path.join(t, "h.csv"))
    code, out = run(tune, "next", "pretend-game")
    check("DONE" in out and "failed at 110" in out and "failed at 3" in out,
          "nothing left to raise past its ceiling: locked")
    st = C.load_state("pretend-game")
    check(st["phase"] == "locked" and st["tuned"]["post"] == 2 and st["tuned"]["screen_pct"] == 4 and
          st["ceilings"] == {"screen_pct": 5, "post": 3}, "the state says so")

    # undo: the start-up script did not exist before, so it is removed
    code, out = run(tune, "undo", "pretend-game")
    check(not os.path.exists(script) and "removed" in out, "undo removes the file The Optimizer made")

    # an .ini setting under a two-bracket header, and an 'ask' setting (BetterVR)
    cemu_dir = os.path.join(t, "BotW")
    os.makedirs(os.path.join(cemu_dir, "BetterVR"))
    os.makedirs(os.path.join(cemu_dir, "portable"))
    ini = os.path.join(cemu_dir, "portable", "BetterVR_settings.ini")
    original = "[Window][Debug]\r\nPos=60,60\r\n\r\n[BetterVR][Settings]\r\nCameraMode=FIRST_PERSON\r\nFoveatedRendering=ON\r\n"
    with open(ini, "w", newline="") as f:
        f.write(original)
    cemu = os.path.join(cemu_dir, "Cemu.exe")
    open(cemu, "wb").close()
    check(tune.guess_profile(cemu) == "botw-bettervr", "Cemu with a BetterVR folder gets the BetterVR profile")
    code, out = run(tune, "start", "botw", "--exe", cemu, "--asked", "resolution=2x")
    check("VR Resolution Multiplier: 2x" in out and "Foveated rendering (sharp middle, softer edges): ON" in out,
          "start reads the .ini and takes the menu setting it was told")
    p = C.load_profile("botw-bettervr")
    fov = [k for k in p["knobs"] if k["id"] == "foveated"][0]
    K.set_value(fov, "OFF", {"exe": cemu}, "botw")
    text = open(ini, newline="").read()
    check("FoveatedRendering=OFF\r\n" in text and "CameraMode=FIRST_PERSON\r\n" in text and "Pos=60,60" in text,
          "an .ini change keeps every other line and the file's line endings")
    res = [k for k in p["knobs"] if k["id"] == "resolution"][0]
    _, ask = K.set_value(res, "1.75x", {"exe": cemu}, "botw")
    check(ask and "VR Resolution Multiplier" in ask and "python -m engine.cli set botw resolution 1.75x" in ask,
          "a menu setting is said, with the command that records it")
    run(tune, "set", "botw", "resolution", "1.75x")
    check(C.load_state("botw")["levels"]["resolution"] == 4, "set records a step picked by hand")
    run(tune, "undo", "botw")
    check(open(ini, newline="").read() == original, "undo puts the .ini back byte for byte")

    # the meter switch (a fake registry, a pretend built meter)
    dist = os.path.join(t, "dist")
    os.makedirs(dist)
    for n in ("lanes_tune_meter.dll", "lanes_tune_meter.json"):
        open(os.path.join(dist, n), "w").close()
    os.environ["OPTIMIZER_METER_DIST"] = dist
    code, out = run(tune, "meter", "on", exe)
    reg = json.load(open(os.environ["OPTIMIZER_FAKEREG"]))
    settings = open(os.path.join(C.layer_dir(), "lanes_tune_meter.txt")).read()
    check(code == 0 and len(reg) == 1 and "exe = Pretend-Win64-Shipping.exe" in settings, "meter on: registered, one game")
    check(f"out = {C.meter_dir()}" in settings, "the meter is told to write into The Optimizer's own folder")
    code, out = run(tune, "meter", "off", exe)
    check(json.load(open(os.environ["OPTIMIZER_FAKEREG"])) == {} and "on = 0" in
          open(os.path.join(C.layer_dir(), "lanes_tune_meter.txt")).read(), "meter off for the last game: unregistered")
    exe32 = os.path.join(t, "old.exe")
    with open(exe32, "wb") as f:
        f.write(b"MZ" + b"\0" * 58 + struct.pack("<I", 64) + b"PE\0\0" + struct.pack("<H", 0x14c) + b"\0" * 32)
    code, out = run(tune, "meter", "on", exe32)
    check(code == 1 and "32-bit" in out, "a 32-bit game is refused (the meter is 64-bit)")

    srv.shutdown()
    print("engine_test: " + ("all passed" if not fails else f"{fails} FAILED"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
