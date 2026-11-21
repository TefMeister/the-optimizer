"""knobs.py - reading and changing one game setting ("knob") the way its profile says, with a backup first.

Kinds of setting (a profile's "kind"):
  ini             a key in an .ini-style file; "section" is the whole header line as written ("[BetterVR][Settings]")
  json            a key in a JSON file, dotted for nesting ("steamvr.supersampleScale"); "also" sets fixed keys with it
  console_script  a file of console lines "<name> <value>" run when the game starts (UEVR's user_script.txt)
  ask             a setting only the game's own menu (or a launcher) can change: The Optimizer says which step to pick,
                  and `python -m engine.cli set <game> <knob> <step>` records what was picked
A knob with "live": "uevr_http" is also sent to the running game at once through the UEVR connector's local port,
so it needs no restart.

Backups: the first time a file is changed for a game it is copied to <game>\\backup\\ with its checksum in
manifest.json; `python -m engine.cli undo <game>` puts every file back (or removes one that did not exist before).
"""
import hashlib
import json
import os
import re
import shutil
import urllib.request

from engine import settings as C

UEVR_URL = "http://127.0.0.1:8899/api/console/command"


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
    if kind == "console_script":
        val = None
        for line in text.splitlines():
            parts = line.strip().split(None, 1)
            if len(parts) == 2 and parts[0].lower() == knob["key"].lower():
                val = parts[1].strip()
        return val
    return None


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
    if kind == "ask":
        where = knob.get("where", "the game's own options")
        return None, f"set {knob['label']} to '{value}' in {where}, then: python -m engine.cli set {game_name} {knob['id']} {value}"
    path = C.expand(knob["file"], game)
    if kind == "console_script" and not os.path.isdir(os.path.dirname(path)):
        raise SystemExit(f"optimizer: {knob['label']}: the folder for {path} is not there (has the game run with UEVR once?)")
    backup_once(game_name, path)
    text = _read(path)
    nl = "\r\n" if text and "\r\n" in text else "\n"
    if kind == "ini":
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
def push_live(knob, value):
    """Send one setting to the running game. (True, what it said) or (False, why not)."""
    if knob.get("live") != "uevr_http":
        return False, "this setting cannot be changed while the game runs"
    url = os.environ.get("OPTIMIZER_UEVR_URL") or UEVR_URL
    body = json.dumps({"command": f"{knob['key']} {value}"}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=C.NET_TIMEOUT_S) as r:
            return 200 <= r.status < 300, r.read(300).decode("utf-8", "replace")
    except OSError as e:
        return False, f"the UEVR connector did not answer ({e})"
