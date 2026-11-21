"""knobs.py - reading and changing one game setting ("knob") the way its profile says, with a backup first.

Kinds of setting (a profile's "kind"):
  ini             a key in an .ini-style file; "section" is the whole header line as written ("[BetterVR][Settings]")
  json            a key in a JSON file, dotted for nesting ("steamvr.supersampleScale"); "also" sets fixed keys with it
  console_script  a file of console lines "<name> <value>" run when the game starts (UEVR's user_script.txt)
  ask             a setting only the game's own menu (or a launcher) can change: The Optimizer says which step to pick,
                  and `python -m engine.cli set <game> <knob> <step>` records what was picked
  gsa_option      one ("<key>", <n>) pair inside an .ini's GFXSettings=(GsaOptions=(...)) line (Silent Hill 2's own
                  options); "map" may give each step a display name ({"2": "Balanced"})
  live_cvar       a value that lives only in the running game (no file): read and changed through the connector
A knob with "live": "uevr_http" is read from, and may be sent to, the running game through the UEVR connector's local
port. Flags (2026-11-21, from the Silent Hill 2 reader's findings):
  live_safe       may be changed while the game runs (without it a live change is refused, the file waits for a start)
  rebuilds        changing it live rebuilds something heavy (SH2's r.ScreenPercentage rebuilds DLSS): never live
  game_owned      the game writes its own value over the file at every start, so the file is never read for it
Start values come from the truth first (start_value): the running game, then the file (not for game_owned), then the
profile's default, else unknown.

Backups: the first time a file is changed for a game it is copied to <game>\\backup\\ with its checksum in
manifest.json; `python -m engine.cli undo <game>` puts every file back (or removes one that did not exist before).
"""
import hashlib
import json
import os
import re
import shutil
import urllib.parse
import urllib.request

from engine import settings as C

UEVR_BASE = "http://127.0.0.1:8899"      # UEVR-MCP's local port
GSA_PAIR = r'\(\s*"{key}"\s*,\s*(-?\d+(?:\.\d+)?)\s*\)'


# ---- steps -----------------------------------------------------------------------------------------------------
def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def step_index(knob, value):
    """Which of the knob's steps a value is (exact, else the nearest number); None when it is none of them."""
    if value is None:
        return None
    steps = [str(s) for s in knob["steps"]]
    v = str(value).strip()
    for i, s in enumerate(steps):
        if s.lower() == v.lower():
            return i
    n = _num(v)
    nums = [_num(s) for s in steps]
    if n is None or any(x is None for x in nums):
        return None
    return min(range(len(nums)), key=lambda i: abs(nums[i] - n))


# ---- reading ---------------------------------------------------------------------------------------------------
def _read(path):
    try:
        with open(path, encoding="utf-8-sig", errors="replace", newline="") as f:   # keep the file's line endings
            return f.read()
    except OSError:
        return None


def get_value(knob, game):
    kind = knob["kind"]
    if kind == "ask":
        return game.get("asked", {}).get(knob["id"])
    if kind == "live_cvar":
        return None
    path = C.expand(knob["file"], game)
    text = _read(path)
    if text is None:
        return None
    if kind == "ini":
        sec, cur = knob.get("section"), None
        for line in text.splitlines():
            s = line.strip()
            if s.startswith("["):
                cur = s
                continue
            if (sec is None or cur == sec) and "=" in s:
                k, _, v = s.partition("=")
                if k.strip() == knob["key"]:
                    return v.strip()
        return None
    if kind == "json":
        try:
            d = json.loads(text)
        except ValueError:
            return None
        for part in knob["key"].split("."):
            if not isinstance(d, dict) or part not in d:
                return None
            d = d[part]
        return json.dumps(d) if isinstance(d, bool) else str(d)
    if kind == "gsa_option":
        m = _gsa_match(text, knob["key"])
        return m.group(1) if m else None
    if kind == "console_script":
        val = None
        for line in text.splitlines():
            parts = line.strip().split(None, 1)
            if len(parts) == 2 and parts[0].lower() == knob["key"].lower():
                val = parts[1].strip()
        return val
    return None


def _gsa_match(text, key):
    """The ("key", n) pair inside a GFXSettings=(GsaOptions=(...)) line; None when it is not there."""
    for m in re.finditer(r"^[ \t]*GFXSettings=.*$", text, re.M):
        p = re.compile(GSA_PAIR.format(key=re.escape(key)))
        hit = p.search(text, m.start(), m.end())
        if hit:
            return hit
    return None


def live_value(knob):
    """The setting's value in the running game, through the connector; None when it does not answer."""
    if knob.get("live") != "uevr_http":
        return None
    url = _base() + "/api/console/cvar?name=" + urllib.parse.quote(knob["key"])
    try:
        with urllib.request.urlopen(url, timeout=C.NET_TIMEOUT_S) as r:
            d = json.loads(r.read(2000).decode("utf-8", "replace"))
    except (OSError, ValueError):
        return None
    for field in ("float", "value", "int", "string"):
        if isinstance(d, dict) and d.get(field) is not None:
            v = d[field]
            if isinstance(v, float) and v.is_integer():
                v = int(v)
            return str(v)
    return None


def start_value(knob, game):
    """(value, where from): "live" (the running game), "file" (the game's own settings file), "default" (the
    profile's), or "unknown". A connector that does not answer is not an error: the next source is tried."""
    v = live_value(knob)
    if v is not None:
        return v, "live"
    if not knob.get("game_owned"):
        v = get_value(knob, game)
        if v is not None:
            return v, "file"
    if "default" in knob:
        return str(knob["steps"][int(knob["default"])]), "default"
    return None, "unknown"


def shown(knob, value):
    """A step as a person reads it: "2 (Balanced)" when the knob maps it to a name."""
    name = (knob.get("map") or {}).get(str(value))
    return f"{value} ({name})" if name else str(value)


# ---- backups ---------------------------------------------------------------------------------------------------
def _manifest_path(game_name):
    return os.path.join(C.game_dir(game_name), "backup", "manifest.json")


def _load_manifest(game_name):
    try:
        with open(_manifest_path(game_name), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def backup_once(game_name, path):
    man = _load_manifest(game_name)
    if path in man:
        return
    bdir = os.path.dirname(_manifest_path(game_name))
    os.makedirs(bdir, exist_ok=True)
    entry = {"existed": os.path.isfile(path)}
    if entry["existed"]:
        dest = os.path.join(bdir, f"{len(man):02d}_" + re.sub(r"[^A-Za-z0-9._-]+", "_", os.path.basename(path)))
        shutil.copy2(path, dest)
        entry.update({"backup": dest, "sha256": _sha(dest)})
    man[path] = entry
    with open(_manifest_path(game_name), "w", encoding="utf-8") as f:
        json.dump(man, f, indent=1)


def restore_all(game_name):
    """Put every backed-up file back. Returns one line per file."""
    out = []
    for path, e in _load_manifest(game_name).items():
        if e.get("existed"):
            if _sha(e["backup"]) != e["sha256"]:
                out.append(f"NOT restored (the backup changed since it was made): {path}")
                continue
            shutil.copy2(e["backup"], path)
            out.append(f"restored: {path}")
        elif os.path.isfile(path):
            os.remove(path)
            out.append(f"removed (The Optimizer made it): {path}")
    return out


# ---- changing --------------------------------------------------------------------------------------------------
def _write(path, text):
    tmp = path + ".optimizer-tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    os.replace(tmp, path)


def _json_value(v):
    try:
        return json.loads(v)
    except (TypeError, ValueError):
        return v


def set_value(knob, value, game, game_name):
    """Write one step. Returns (changed_file_or_None, a line for the person when the menu must do it)."""
    kind = knob["kind"]
    if kind == "live_cvar":
        return None, None             # nothing on disk: it is sent live (when safe) by the caller
    if kind == "ask":
        where = knob.get("where", "the game's own options")
        return None, f"set {knob['label']} to '{value}' in {where}, then: python -m engine.cli set {game_name} {knob['id']} {value}"
    path = C.expand(knob["file"], game)
    if kind == "console_script" and not os.path.isdir(os.path.dirname(path)):
        raise SystemExit(f"optimizer: {knob['label']}: the folder for {path} is not there (has the game run with UEVR once?)")
    backup_once(game_name, path)
    text = _read(path)
    nl = "\r\n" if text and "\r\n" in text else "\n"
    if kind == "gsa_option":
        m = _gsa_match(text or "", knob["key"])
        if not m:
            raise SystemExit(f"optimizer: {knob['label']}: no ({knob['key']}, ...) pair in {path}'s GFXSettings line")
        _write(path, text[:m.start(1)] + str(value) + text[m.end(1):])
    elif kind == "ini":
        _write(path, _ini_set(text or "", knob.get("section"), knob["key"], str(value), nl))
    elif kind == "json":
        d = json.loads(text) if text else {}
        _json_set(d, knob["key"], _json_value(str(value)))
        for k, v in (knob.get("also") or {}).items():
            _json_set(d, k, v)
        _write(path, json.dumps(d, indent=3) + nl)
    elif kind == "console_script":
        lines = (text or "").splitlines()
        new, done = [], False
        for line in lines:
            parts = line.strip().split(None, 1)
            if parts and parts[0].lower() == knob["key"].lower():
                if not done:
                    new.append(f"{knob['key']} {value}")
                    done = True
                continue
            new.append(line)
        if not done:
            new.append(f"{knob['key']} {value}")
        _write(path, nl.join(new) + nl)
    return path, None


def _ini_set(text, section, key, value, nl):
    lines = text.splitlines()
    cur, sec_at, out, done = None, None, [], False
    for line in lines:
        s = line.strip()
        if s.startswith("["):
            if sec_at is not None and not done and cur == section:
                out.append(f"{key}={value}")          # the key was not in its section: add it at the section's end
                done = True
            cur = s
            if s == section:
                sec_at = len(out)
        elif not done and (section is None or cur == section) and "=" in s and s.partition("=")[0].strip() == key:
            out.append(line[:line.index("=") + 1] + value)
            done = True
            continue
        out.append(line)
    if not done:
        if section and sec_at is None:
            out += ([""] if out and out[-1].strip() else []) + [section]
        out.append(f"{key}={value}")
    return nl.join(out) + nl


def _json_set(d, dotted, value):
    parts = dotted.split(".")
    for p in parts[:-1]:
        d = d.setdefault(p, {})
    d[parts[-1]] = value


# ---- live ------------------------------------------------------------------------------------------------------
def _base():
    return (os.environ.get("OPTIMIZER_UEVR_BASE") or UEVR_BASE).rstrip("/")


def live_ok(knob):
    """May this setting be changed while the game runs? Only when marked safe live, and never one that rebuilds."""
    return knob.get("live") == "uevr_http" and bool(knob.get("live_safe")) and not knob.get("rebuilds")


def push_live(knob, value):
    """Send one setting to the running game. (True, what it said) or (False, why not)."""
    if knob.get("live") != "uevr_http":
        return False, "this setting cannot be changed while the game runs"
    if knob.get("rebuilds"):
        return False, "changing this one live rebuilds part of the picture (a known crash risk): it waits for a start"
    if not knob.get("live_safe"):
        return False, "this setting is not marked safe to change live: it waits for the next start"
    url = _base() + "/api/console/command"
    body = json.dumps({"command": f"{knob['key']} {value}"}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=C.NET_TIMEOUT_S) as r:
            return 200 <= r.status < 300, r.read(300).decode("utf-8", "replace")
    except OSError as e:
        return False, f"the UEVR connector did not answer ({e})"
