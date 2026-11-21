"""game.py - the toolbox's hands on the game: find the launcher, launch, quit by the game's own quit (never a kill),
the connector, save swaps through the pack's own swapper, the claim check, crash signs, and the toolbox log.

Every program this file starts is written to <OPTIMIZER_DIR>/<game>/toolbox.log first, so a run can always be read
back: what was started, with what, and when.
"""
import glob
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

from engine import pack as P
from engine import settings as C

DETACHED = 0x00000008 | 0x00000200          # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP: the game outlives us


def log(game, text):
    os.makedirs(C.game_dir(game), exist_ok=True)
    with open(os.path.join(C.game_dir(game), "toolbox.log"), "a", encoding="utf-8") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + text + "\n")


def _x(text):
    return os.path.expandvars(text)


# ---- finding things --------------------------------------------------------------------------------------------
def launcher(pack):
    """The launcher's full path, or None: the pack's search places, then beside the game, then inside the pack."""
    la = pack.get("launch") or {}
    for g in la.get("find") or []:
        hits = sorted(glob.glob(_x(g)))
        if hits:
            return hits[0]
    exe = P.exe_path(pack)
    prog = la.get("program") or ""
    if exe and prog and os.path.isfile(os.path.join(os.path.dirname(exe), prog)):
        return os.path.join(os.path.dirname(exe), prog)
    inside = os.path.join(P.pack_dir(pack["name"]), prog)
    return inside if prog and os.path.isfile(inside) else None


def missing_vr_files(pack, where):
    return [f for f in pack.get("vr_files") or [] if not os.path.isfile(os.path.join(os.path.dirname(where), f))]


def claimed_by(pack):
    """Who holds this game (a modding session), or None. Lanes' claim when Lanes is set up here, else our own file."""
    try:
        with open(os.path.join(C.base_dir(), "claim.json"), encoding="utf-8") as f:
            c = json.load(f)
        if c.get("game") == pack["name"]:
            return c.get("by") or "another session"
    except (OSError, ValueError):
        pass
    prefix = pack.get("lanes_prefix")
    mem = C.conf("claude_memory") or (os.path.join(C.conf("root"), "claude-memory") if C.conf("root") else None)
    if mem and prefix:
        try:
            with open(os.path.join(mem, "status", prefix + ".md"), encoding="utf-8") as f:
                for line in f:
                    if line.startswith("LIVE:"):
                        parts = line.split()
                        stamp = time.mktime(time.strptime(" ".join(parts[2:4]), "%Y-%m-%d %H:%M"))
                        if time.time() - stamp < C.CLAIM_FRESH_S:
                            return f"a Lanes session ({parts[1]} since {' '.join(parts[2:4])})"
        except (OSError, ValueError, IndexError):
            pass
    return None


# ---- the connector ---------------------------------------------------------------------------------------------
def _base():
    return (os.environ.get("OPTIMIZER_UEVR_BASE") or "http://127.0.0.1:8899").rstrip("/")


def connector_up(pack):
    url = _x((pack.get("connector") or {}).get("check_url") or (_base() + "/api/console/cvar?name=r.ScreenPercentage"))
    try:
        with urllib.request.urlopen(url, timeout=C.NET_TIMEOUT_S):
            return True
    except urllib.error.HTTPError:
        return True                    # it answered
    except OSError:
        return False


def console(game, line):
    """One console line to the running game through its connector. (ok, what it said)"""
    log(game, f"console: {line}")
    body = json.dumps({"command": line}).encode()
    req = urllib.request.Request(_base() + "/api/console/command", data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=C.NET_TIMEOUT_S) as r:
            return 200 <= r.status < 300, r.read(300).decode("utf-8", "replace")
    except OSError as e:
        return False, f"the connector did not answer ({e})"


# ---- launch and quit -------------------------------------------------------------------------------------------
def launch(pack, where, headset=False):
    la = pack.get("launch") or {}
    args = list(la.get("args_headset" if headset else "args") or [])
    cmd = ([sys.executable, where] if where.lower().endswith(".py") else [where]) + args
    env = dict(os.environ)
    env.update({k: _x(str(v)) for k, v in (la.get("env") or {}).items()})
    log(pack["name"], "launch: " + " ".join(cmd))
    kw = {"creationflags": DETACHED} if os.name == "nt" else {"start_new_session": True}
    subprocess.Popen(cmd, cwd=os.path.dirname(where), env=env, stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kw)
    _mark_log_start(pack)


def wait_running(pack, want, seconds):
    exe = P.exe_path(pack) or pack["exe"]
    t0 = time.time()
    while time.time() - t0 < seconds:
        if C.game_running(exe) == want:
            return True
        time.sleep(0.25)
    return C.game_running(exe) == want


def quit_game(pack):
    """The game's own quit, then a wait. Never a kill: a game that will not close is reported, not ended."""
    q = pack.get("quit") or {}
    exe = P.exe_path(pack) or pack["exe"]
    if not C.game_running(exe):
        return True, "the game was not running"
    if q.get("connector_console"):
        log(pack["name"], f"quit: the game's own quit through the connector ({q['connector_console']})")
        ok, said = console(pack["name"], q["connector_console"])
        if not ok:
            return False, f"the game's own quit could not be sent: {said}. Not killed: it is still running"
    elif q.get("route"):
        helper = os.path.join(C.helpers_dir(), "menu_o_matic.py")
        log(pack["name"], f"quit: the menu route {q['route']} ({helper})")
        subprocess.run([sys.executable, helper, "run", q["route"]], capture_output=True, timeout=300)
    else:
        return False, "the pack has no quit of the game's own: not killed, still running"
    if wait_running(pack, False, C.QUIT_WAIT_S):
        return True, "the game closed by its own quit"
    return False, (f"the game is still running {C.QUIT_WAIT_S:g} s after its own quit. It was NOT killed; "
                   f"it needs the person")


# ---- save swaps (the pack's own swapper) -----------------------------------------------------------------------
def _swap(pack, *args):
    tool = os.path.join(P.pack_dir(pack["name"]), pack.get("swap_tool") or "")
    if not pack.get("swap_tool") or not os.path.isfile(tool):
        return False, "this pack has no save swapper"
    log(pack["name"], "swap: " + " ".join(args))
    r = subprocess.run([sys.executable, tool, *args], capture_output=True, text=True, timeout=120)
    said = (r.stdout + r.stderr).strip().splitlines()
    return r.returncode == 0, said[-1] if said else ""


def swap_in_force(pack):
    ok, said = _swap(pack, "status")
    return ok and "in force" in said and "no swap" not in said


def swap_start(pack, slot):
    return _swap(pack, "start", f"slot={slot}")


def swap_end(pack):
    return _swap(pack, "end")


# ---- crash signs -----------------------------------------------------------------------------------------------
def _crash_log(pack):
    return _x((pack.get("crash_signs") or {}).get("log") or "")


def _mark_log_start(pack):
    path = _crash_log(pack)
    size = os.path.getsize(path) if path and os.path.isfile(path) else 0
    with open(os.path.join(C.game_dir(pack["name"]), "crashlog.json"), "w", encoding="utf-8") as f:
        json.dump({"path": path, "from": size}, f)


def crash_seen(pack):
    """The first crash-sign line written since the last launch, or None."""
    try:
        with open(os.path.join(C.game_dir(pack["name"]), "crashlog.json"), encoding="utf-8") as f:
            m = json.load(f)
        with open(m["path"], encoding="utf-8", errors="replace") as f:
            f.seek(m["from"] if os.path.getsize(m["path"]) >= m["from"] else 0)
            text = f.read()
    except (OSError, ValueError, KeyError):
        return None
    for sign in (pack.get("crash_signs") or {}).get("lines") or []:
        if sign in text:
            return sign
    return None
