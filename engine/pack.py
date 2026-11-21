"""pack.py - game packs: one folder per game in packs/, holding everything the AI needs to run that game with nobody
at the PC (pack.json, plus any tool the pack ships, such as a save swapper).

pack.json fields (every one is checked by check(); "say" lines are plain words for the person):
  name, label        the folder's name, and the game's name as a person reads it
  exe                the game's program name (what runs, what the meter and State-o-matiC look for)
  find_exe           where the game is: {"steam_app": <id>, "steam_folder": "<folder in steamapps/common>",
                     "rel": "<the program inside that folder>"} and/or {"globs": [...]}
  launch             {"program": <the launcher: a name found next to the game, in "find", or a pack tool>,
                     "find": [globs], "args": [...], "args_headset": [...], "env": {...}}
  vr_files           files a VR launch needs, relative to the launcher's folder (launch is refused without them)
  to_play            the steps from launch to play: a list of {"do": "key"|"connector_call"|"wait"|"vr_trigger"|
                     "route", ...}, or a Menu-o-matiC route name
  quit               the game's own quit: {"connector_console": "quit"} or {"route": "<name>"}; never a kill
  settings           the knob list, in the profile format (knobs.py), each knob with "keep": the file the game reads at
                     its start, or null = lives only while the game runs
  spots_find         {"save_glob", "slot_re", "reach": "save_slot"} and/or {"levels": [...], "reach": "console"|...}
  swap_tool          the save swapper the pack ships (a file inside the pack), when spots are save slots
  godmode            null, or {"console": "<line>"}
  connector          {"name", "mcp_name", "mcp_command", "check_url", "get"}: the game's live connector
  crash_signs        {"log": <file>, "lines": [...]}: log lines that mean the known start crash
  picture            {"w": <px>, "h": <px>} per eye, for the pretend headset
  settle             seconds the frame time must stay steady after arriving (default 5)
"""
import glob
import json
import os
import re

from engine import settings as C

PACKS_DIR = os.path.join(C.ROOT, "packs")
REQUIRED = [
    ("name", "no name"),
    ("label", "no label (the game's name as a person reads it)"),
    ("exe", "no program name (exe)"),
    ("find_exe", "no way to find the game on this PC (find_exe)"),
    ("launch", "no way to launch the game (launch)"),
    ("vr_files", "no list of the files a VR launch needs (vr_files)"),
    ("to_play", "no way from the launch into play (to_play)"),
    ("quit", "no way to quit the game by its own means"),
    ("settings", "no settings to tune"),
    ("spots_find", "no way to find the game's spots (spots_find)"),
    ("connector", "no live connector named (connector)"),
    ("crash_signs", "no crash signs (crash_signs: the log lines that mean the known start crash)"),
    ("picture", "no headset picture size for the pretend headset (picture)"),
]


def packs_dir():
    return os.environ.get("OPTIMIZER_PACKS_DIR") or PACKS_DIR


def pack_dir(name):
    return os.path.join(packs_dir(), name)


def list_packs():
    d = packs_dir()
    if not os.path.isdir(d):
        return []
    return sorted(n for n in os.listdir(d) if os.path.isfile(os.path.join(d, n, "pack.json")))


def load(name):
    path = os.path.join(pack_dir(name), "pack.json")
    if not os.path.isfile(path):
        raise SystemExit(f"optimizer: there is no game pack '{name}' (there are: {', '.join(list_packs()) or 'none'})")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def check(pack):
    """Every problem in plain words; an empty list = the pack is complete."""
    out = [say for key, say in REQUIRED if key not in pack or pack[key] in ("", [], {})]
    if "godmode" not in pack:
        out.append("no god mode entry (null when the game has none)")
    knobs = (pack.get("settings") or {}).get("knobs") or []
    if pack.get("settings"):
        out += C.check_profile(pack["settings"])
    for k in knobs:
        kid = k.get("id", "?")
        if "keep" not in k:
            out.append(f"{kid}: does not say where it lasts (keep: the file the game reads at its start, or null)")
        if k.get("kind") == "live_cvar" and (not k.get("live_safe") or k.get("rebuilds")):
            out.append(f"{kid}: lives only in the running game but is not marked safe to change live")
    if pack.get("swap_tool") and not os.path.isfile(os.path.join(pack_dir(pack.get("name", "")), pack["swap_tool"])):
        out.append(f"the save swapper {pack['swap_tool']} is not inside the pack")
    return out


def _steam_libraries():
    if os.environ.get("OPTIMIZER_STEAM_LIBS") is not None:
        return [p for p in os.environ["OPTIMIZER_STEAM_LIBS"].split(os.pathsep) if p]
    root = C.conf("steam_root") or C.steam_path()
    libs = [root]
    try:
        with open(os.path.join(root, "steamapps", "libraryfolders.vdf"), encoding="utf-8", errors="replace") as f:
            libs += [p.replace("\\\\", "\\") for p in re.findall(r'"path"\s+"([^"]+)"', f.read())]
    except OSError:
        pass
    seen, out = set(), []
    for p in libs:
        if os.path.normcase(p) not in seen:
            seen.add(os.path.normcase(p))
            out.append(p)
    return out


def exe_path(pack):
    """The game's program on this PC, or None."""
    fe = pack.get("find_exe") or {}
    if fe.get("steam_folder") and fe.get("rel"):
        for lib in _steam_libraries():
            p = os.path.join(lib, "steamapps", "common", fe["steam_folder"], fe["rel"])
            if os.path.isfile(p):
                return p
    for g in fe.get("globs") or []:
        hits = glob.glob(os.path.expandvars(g))
        if hits:
            return hits[0]
    return None


def installed(pack):
    return exe_path(pack) is not None


def rows():
    """What the window lists: every pack with whether its game is here and whether the pack is complete."""
    out = []
    for name in list_packs():
        p = load(name)
        probs = check(p)
        out.append({"name": name, "label": p.get("label", name), "installed": installed(p),
                    "complete": not probs, "problems": probs})
    return out
