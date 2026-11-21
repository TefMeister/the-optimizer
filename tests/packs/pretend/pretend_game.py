"""pretend_game.py - a pretend game for The Optimizer's tests and its dry run: no window, no graphics, nothing real.

While it "runs" it:
  - keeps the running file (OPTIMIZER_RUNNING_FILE) in place, so the toolbox sees the game as running;
  - answers like a game's live connector on OPTIMIZER_UEVR_BASE: GET /api/console/cvar?name=X, POST
    /api/console/command ("quit" quits it; anything else is set as a value);
  - writes frame-meter rows into the meter folder (<OPTIMIZER_DIR>/meter), fast-forwarded so a short look holds
    enough frames: heavy (one frame in ten late) while r.Pretend.Heavy is 1, smooth when it is 0;
  - logs every command it was sent to <home>/pretend-commands.log.
It quits only when told to through its connector: there is no other way out (the toolbox must never kill it).
"""
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HOME = os.path.dirname(os.path.abspath(__file__))
RUNNING = os.environ["OPTIMIZER_RUNNING_FILE"]
BASE = os.environ["OPTIMIZER_UEVR_BASE"]
METER = os.path.join(os.environ["OPTIMIZER_DIR"], "meter")
LOG = os.path.join(HOME, "pretend-commands.log")
CVARS = {"r.Pretend.Heavy": 1.0, "r.Pretend.Shadow": 1.0}
QUIT = threading.Event()
PERIOD = 13.889


class Connector(BaseHTTPRequestHandler):
    def do_GET(self):
        u = urlparse(self.path)
        name = (parse_qs(u.query).get("name") or [""])[0]
        if u.path != "/api/console/cvar" or name not in CVARS:
            self.send_response(404)
            self.end_headers()
            return
        self._json({"name": name, "float": CVARS[name]})

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        cmd = json.loads(self.rfile.read(n) or b"{}").get("command", "")
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(cmd + "\n")
        parts = cmd.split()
        if parts and parts[0] == "quit":
            QUIT.set()
        elif len(parts) == 2:
            try:
                CVARS[parts[0]] = float(parts[1])
            except ValueError:
                pass
        self._json({"ok": True})

    def _json(self, d):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(json.dumps(d).encode())

    def log_message(self, *a):
        pass


def frames():
    os.makedirs(METER, exist_ok=True)
    path = os.path.join(METER, time.strftime("%Y-%m-%d_%H-%M-%S") + "_pretend_game.frametime.csv")
    t, i = 0.0, 0
    with open(path, "w", encoding="utf-8") as f:
        f.write("# pretend\nt_ms,interval_ms,wait_ms,work_ms,period_ms,missed\n")
        while not QUIT.is_set():
            chunk = []
            for _ in range(100):                     # 100 frames every 0.1 s: fast-forwarded on purpose
                heavy = CVARS.get("r.Pretend.Heavy", 1) >= 1
                iv = PERIOD * 2 if heavy and i % 10 == 0 else PERIOD
                t += iv
                i += 1
                chunk.append(f"{t:.3f},{iv:.3f},2.0,4.000,{PERIOD:.3f},{int(iv > 1.5 * PERIOD)}\n")
            f.write("".join(chunk))
            f.flush()
            QUIT.wait(0.1)


def main():
    u = urlparse(BASE)
    srv = ThreadingHTTPServer((u.hostname, u.port), Connector)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    with open(RUNNING, "w") as f:
        f.write(str(os.getpid()))
    try:
        frames()
    finally:
        srv.shutdown()
        try:
            os.remove(RUNNING)
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
