"""fixes_test.py - the three Tune-o-matiC faults found before its first real run, fixed in The Optimizer:
start values read from the truth (the running game, then the game's own settings file, never a file the game
overwrites), live changes only for settings marked safe live, and undo that never pushes live while the game runs.
A pretend connector, made-up files, a temp folder. Exit 0 = pass."""
import contextlib
import io
import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
fails = 0
SENT = []
LIVE = {}


def check(ok, what):
    global fails
    print(("  ok    " if ok else "FAIL: ") + what)
    fails += not ok


class Connector(BaseHTTPRequestHandler):
    """Answers like UEVR-MCP: GET /api/console/cvar?name=X -> {"float": v}; POST /api/console/command."""
    def do_GET(self):
        u = urlparse(self.path)
        name = (parse_qs(u.query).get("name") or [""])[0]
        if u.path != "/api/console/cvar" or name not in LIVE:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.end_headers()
        self.wfile.write(json.dumps({"name": name, "float": LIVE[name]}).encode())

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        SENT.append(json.loads(self.rfile.read(n))["command"])
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

    def log_message(self, *a):
        pass


def run(cli, *argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = cli.main(list(argv))
    return code, out.getvalue()


def write_profile(d, name, knobs):
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, name + ".json"), "w", encoding="utf-8") as f:
        json.dump({"label": name, "knobs": knobs}, f)


INNER = {"id": "inner", "label": "DLSS inner size", "kind": "live_cvar", "key": "r.ScreenPercentage",
         "steps": ["50", "54", "58", "62", "66.7"], "floor": 0, "shows": 2, "cost": 3, "live": "uevr_http",
         "rebuilds": True, "restart": False}
RT = {"id": "rt", "label": "Ray-traced reflections", "kind": "live_cvar", "key": "r.Lumen.Reflections.HardwareRayTracing",
      "steps": ["0", "1"], "default": 1, "floor": 0, "shows": 1, "cost": 3, "live": "uevr_http", "live_safe": True,
      "restart": False}
GSA_LINE = 'GFXSettings=(GsaOptions=(("Quality", -1),("Adv_DLSSQuality", 2)),Raytracing=On)'


def main():
    t = tempfile.mkdtemp(prefix="optimizer-fixes-")
    os.environ["OPTIMIZER_DIR"] = os.path.join(t, "optimizer")
    os.environ["OPTIMIZER_LANES_CONF"] = os.path.join(t, "lanes.conf")
    os.environ["OPTIMIZER_RUNTIME"] = "virtualdesktop"
    os.environ["OPTIMIZER_NO_GPU"] = "1"
    os.environ["OPTIMIZER_PROFILES_DIR"] = os.path.join(t, "profiles")
    os.environ["APPDATA"] = os.path.join(t, "appdata")
    os.environ["LOCALAPPDATA"] = os.path.join(t, "local")
    srv = HTTPServer(("127.0.0.1", 0), Connector)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    up = f"http://127.0.0.1:{srv.server_port}"
    down = "http://127.0.0.1:9"            # nothing answers there: the connector is down
    os.environ["OPTIMIZER_UEVR_BASE"] = up
    from engine import cli
    from engine import knobs as K

    exe = os.path.join(t, "Game", "Binaries", "Win64", "Pretend-Win64-Shipping.exe")
    os.makedirs(os.path.dirname(exe))
    open(exe, "wb").close()
    ini = os.path.join(t, "local", "Pretend", "GameUserSettings.ini")
    os.makedirs(os.path.dirname(ini))
    original = "[/Script/GameBase.BGameUserSettings]\r\n" + GSA_LINE + "\r\nbUseVSync=False\r\n"
    with open(ini, "w", newline="") as f:
        f.write(original)
    dlss = {"id": "dlss", "label": "DLSS level", "kind": "gsa_option", "file": ini, "key": "Adv_DLSSQuality",
            "steps": ["1", "2", "3"], "map": {"1": "Performance", "2": "Balanced", "3": "Quality"}, "floor": 0,
            "shows": 2, "cost": 3, "game_owned": False, "restart": True}
    script = os.path.join(t, "appdata", "UnrealVRMod", "Pretend-Win64-Shipping", "user_script.txt")
    os.makedirs(os.path.dirname(script))
    with open(script, "w") as f:
        f.write("r.ScreenPercentage 100\n")
    owned = {"id": "owned", "label": "Sharpness the game owns", "kind": "console_script", "file": script,
             "key": "r.ScreenPercentage", "steps": ["50", "58", "100"], "floor": 0, "shows": 2, "cost": 3,
             "live": "uevr_http", "game_owned": True, "restart": False}

    # start_reads_live_first
    LIVE["r.ScreenPercentage"] = 58.0
    val, src = K.start_value(INNER, {"exe": exe})
    check(src == "live" and K.step_index(INNER, val) == 2, "start_reads_live_first: the connector's 58.0 is step 58")
    write_profile(os.environ["OPTIMIZER_PROFILES_DIR"], "fixes", [INNER, RT, dlss])
    code, out = run(cli, "start", "pretend", "--exe", exe, "--profile", "fixes")
    check(code == 0 and "DLSS inner size: 58 (read live)" in out, "start_reads_live_first: start says so")

    # start_falls_back_when_connector_down
    os.environ["OPTIMIZER_UEVR_BASE"] = down
    try:
        val, src = K.start_value(dlss, {"exe": exe})
        check(src == "file" and K.step_index(dlss, val) == 1, "start_falls_back_when_connector_down: index 1 from the file")
        code, out = run(cli, "start", "pretend", "--exe", exe, "--profile", "fixes")
        check("DLSS level: 2 (Balanced) (from the game's settings file)" in out,
              "start_falls_back_when_connector_down: start says where it read it")
    except Exception as e:                     # noqa: BLE001 - the test is that nothing is raised
        check(False, f"start_falls_back_when_connector_down raised {e!r}")

    # game_owned_never_reads_user_script
    val, src = K.start_value(owned, {"exe": exe})
    check(src == "unknown" and val is None, "game_owned_never_reads_user_script: the 100 in user_script.txt is ignored")

    # gsa_option_write_keeps_the_rest
    path, _ = K.set_value(dlss, "3", {"exe": exe}, "pretend")
    text = open(ini, newline="").read()
    check(path == ini and text == original.replace('("Adv_DLSSQuality", 2)', '("Adv_DLSSQuality", 3)'),
          "gsa_option_write_keeps_the_rest: only the pair changes, byte for byte")
    man = json.load(open(os.path.join(os.environ["OPTIMIZER_DIR"], "pretend", "backup", "manifest.json")))
    check(ini in man and open(man[ini]["backup"], newline="").read() == original,
          "gsa_option_write_keeps_the_rest: a backup was made first")

    # live_change_refused_unless_live_safe
    os.environ["OPTIMIZER_UEVR_BASE"] = up
    SENT.clear()
    ok1, _ = K.push_live(INNER, "50")                        # rebuilds: never live
    ok2, _ = K.push_live({**RT, "live_safe": False}, "0")    # not marked safe
    ok3, _ = K.push_live(RT, "0")                            # safe live
    check(not ok1 and not ok2 and ok3 and SENT == ["r.Lumen.Reflections.HardwareRayTracing 0"],
          "live_change_refused_unless_live_safe: only the safe one is sent")

    # undo_no_live_push_while_running
    SENT.clear()
    os.environ["OPTIMIZER_FAKE_RUNNING"] = "1"
    code, out = run(cli, "undo", "pretend")
    check(SENT == [] and "restart the game" in out and open(ini, newline="").read() == original,
          "undo_no_live_push_while_running: files back, nothing sent, restart said")
    os.environ["OPTIMIZER_FAKE_RUNNING"] = "0"

    srv.shutdown()
    print("fixes_test: " + ("all passed" if not fails else f"{fails} FAILED"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
