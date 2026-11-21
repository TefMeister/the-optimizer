"""settings.py - where The Optimizer keeps things, its numbers (named once, each with why), and the per-game state.

Everything a run leaves is under %LOCALAPPDATA%\\TheOptimizer\\ (OPTIMIZER_DIR in tests):
  meter\\                 the frame meter's files (one CSV per VR session, <exe>.live.json while it runs)
  meter-layer\\           the installed copy of the meter (the DLL, its manifest, lanes_tune_meter.txt)
  <game>\\state.json      one game's tuning: its profile, each setting's step now and at the start, what was tried
  <game>\\backup\\        the game's own settings files as they were before The Optimizer first touched them
(The meter keeps its first name, lanes_tune_meter, from when it was built inside Lanes as Tune-o-matiC.)
"""
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PROFILES_DIR = os.path.join(HERE, "profiles")
METER_SRC = os.path.join(ROOT, "meter")

# ---- the numbers, named once -----------------------------------------------------------------------------------
DEFAULT_TARGET_FPS = 72          # Tefa, 2026-11-21: "the graphics never go lower than 72fps"
HOLD_MISSED_PCT = 1.0            # a test holds when at most 1 frame in 100 was late ...
HOLD_LOW_SHARE = 0.97            # ... and the slowest 1% of frames still ran at 97% of the target rate
ROOM_GPU_PCT = 80                # holding with the graphics card under 80% busy: room to make it look better
GPU_BOUND_PCT = 90               # failing with the card at 90% or more: the card is the limit (else the processor)
ROOM_WORK_SHARE = 0.75           # no card numbers: the game's own frame work under 75% of a frame counts as room
MIN_FRAMES = 300                 # fewer frames than this (about 4 s at 72 Hz) is too short to judge
MAX_STEPS = 40                   # a tuning that has not settled after this many changes stops and says so
NVSMI_EVERY_S = 1.0              # one graphics-card sample a second while measuring
NET_TIMEOUT_S = 3                # a live change sent to a game's connector gives up after this


def base_dir():
    return os.environ.get("OPTIMIZER_DIR") or os.path.join(
        os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "TheOptimizer")


def meter_dir():
    return os.path.join(base_dir(), "meter")


def layer_dir():
    return os.path.join(base_dir(), "meter-layer")


def game_dir(game):
    return os.path.join(base_dir(), slug(game))


def slug(name):
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not s:
        raise SystemExit(f"optimizer: '{name}' is not a usable game name")
    return s


def conf(key, default=None):
    """One value from Lanes' lanes.conf when Lanes is on this PC (OPTIMIZER_LANES_CONF in tests); the last line
    naming it wins. Without Lanes every value is its default."""
    path = os.environ.get("OPTIMIZER_LANES_CONF") or os.path.join(os.path.expanduser("~"), ".claude", "lanes.conf")
    val = default
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.lstrip().startswith("#"):
                    continue
                m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_.-]*)\s*=\s*(.*?)\s*(#.*)?$", line)
                if m and m.group(1) == key:
                    val = m.group(2).strip().strip('"').strip("'")
    except OSError:
        pass
    return val


# ---- profiles --------------------------------------------------------------------------------------------------
def profile_names():
    return sorted(n[:-5] for n in os.listdir(PROFILES_DIR) if n.endswith(".json"))


def load_profile(name):
    path = os.path.join(PROFILES_DIR, name + ".json")
    if not os.path.isfile(path):
        raise SystemExit(f"optimizer: no profile '{name}' (there are: {', '.join(profile_names())})")
    with open(path, encoding="utf-8") as f:
        p = json.load(f)
    problems = check_profile(p)
    if problems:
        raise SystemExit(f"optimizer: profile '{name}' is broken: " + "; ".join(problems))
    return p


KINDS = ("ini", "json", "console_script", "ask")


def check_profile(p):
    out = []
    ids = set()
    for k in p.get("knobs", []):
        kid = k.get("id", "?")
        if kid in ids:
            out.append(f"{kid}: id used twice")
        ids.add(kid)
        if k.get("kind") not in KINDS:
            out.append(f"{kid}: kind must be one of {', '.join(KINDS)}")
        steps = k.get("steps") or []
        if len(steps) < 2:
            out.append(f"{kid}: needs two steps or more, cheapest first")
        if not 0 <= int(k.get("floor", 0)) < max(len(steps), 1):
            out.append(f"{kid}: floor is not one of its steps")
        for field in ("shows", "cost"):
            if not 0 <= int(k.get(field, -1)) <= 3:
                out.append(f"{kid}: {field} must be 0 (none) to 3 (a lot)")
        if k.get("kind") != "ask" and not k.get("file"):
            out.append(f"{kid}: a {k.get('kind')} setting needs its file")
    return out


def steam_path():
    """Steam's folder from the registry (where Steam itself says it is), else its usual place."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
            return os.path.normpath(winreg.QueryValueEx(k, "SteamPath")[0])
    except (ImportError, OSError):
        return r"C:\Program Files (x86)\Steam"


def expand(text, game):
    """{exe_dir}, {exe_stem}, {steam} and %ENV% in a profile's file paths."""
    exe = game.get("exe") or ""
    rep = {
        "{exe_dir}": os.path.dirname(exe),
        "{exe_stem}": os.path.splitext(os.path.basename(exe))[0],
        "{steam}": conf("steam_root") or steam_path(),
    }
    for k, v in game.get("paths", {}).items():
        rep["{" + k + "}"] = v
    for k, v in rep.items():
        text = text.replace(k, v)
    return os.path.expandvars(text)


# ---- the state of one game's tuning ----------------------------------------------------------------------------
def state_path(game):
    return os.path.join(game_dir(game), "state.json")


def load_state(game):
    path = state_path(game)
    if not os.path.isfile(path):
        raise SystemExit(f"optimizer: '{game}' has not been started (python -m engine.cli start {game} --exe <the game's program>)")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_state(state):
    d = game_dir(state["game"])
    os.makedirs(d, exist_ok=True)
    tmp = state_path(state["game"]) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=1)
    os.replace(tmp, state_path(state["game"]))


def note(state, text):
    state.setdefault("history", []).append({"when": time.strftime("%Y-%m-%d %H:%M:%S"), "what": text})


def say(*lines):
    for line in lines:
        print(line)
    sys.stdout.flush()
