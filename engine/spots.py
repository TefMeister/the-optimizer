"""spots.py - the spots of one game: the places the tour visits and measures (a save slot, a console line, a level jump).

The robot finds them from the game pack (every save slot on this PC, every level the pack lists); the person can add
one, name one, or strike one out. Kept in <OPTIMIZER_DIR>/<game>/spots.json as a list of
  {"id", "label", "by": "robot"|"person", "struck": bool, "gone": bool,
   "reach": {"kind": "save_slot"|"console"|"level_jump"|"route", "value": ...}}
A robot spot whose save file has vanished is marked "gone" (never measured) and comes back when the file does; the
person's strikes and names are never undone by a new search.
"""
import glob
import json
import os
import re

from engine import settings as C


def _path(game):
    return os.path.join(C.game_dir(game), "spots.json")


def load(game):
    try:
        with open(_path(game), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def _save(game, spots):
    os.makedirs(C.game_dir(game), exist_ok=True)
    tmp = _path(game) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(spots, f, indent=1)
    os.replace(tmp, _path(game))


def _found(pack):
    """What the pack says is reachable on this PC now: [(id, label, reach)]."""
    sf = pack.get("spots_find") or {}
    out = []
    if sf.get("save_glob"):
        rx = re.compile(sf.get("slot_re") or r"(\d+)")
        slots = set()
        for p in glob.glob(os.path.expandvars(sf["save_glob"])):
            m = rx.search(os.path.basename(p))
            if m:
                slots.add(int(m.group(1)))
        for n in sorted(slots):
            out.append((f"slot{n}", f"save slot {n} (not named yet)", {"kind": sf.get("reach", "save_slot"), "value": n}))
    for lv in sf.get("levels") or []:
        out.append((lv["id"], lv.get("label", lv["id"]), {"kind": sf.get("level_reach", "level_jump"),
                                                          "value": lv.get("value", lv["id"])}))
    return out


def find(game, pack):
    """Add every spot the pack can reach now that is not on the list yet. Returns how many were added."""
    spots = load(game)
    have = {s["id"]: s for s in spots}
    now = _found(pack)
    now_ids = {sid for sid, _, _ in now}
    added = 0
    for sid, label, reach in now:
        if sid in have:
            have[sid]["gone"] = False
            continue
        spots.append({"id": sid, "label": label, "by": "robot", "struck": False, "gone": False, "reach": reach})
        added += 1
    for s in spots:
        if s["by"] == "robot" and s["id"] not in now_ids:
            s["gone"] = True
    _save(game, spots)
    return added


def active(game):
    """The spots the tour visits, in list order."""
    return [s for s in load(game) if not s.get("struck") and not s.get("gone")]


def get(game, sid):
    for s in load(game):
        if s["id"] == sid:
            return s
    return None


def add(game, label, kind, value):
    spots = load(game)
    n = 1 + sum(1 for s in spots if s["by"] == "person")
    sid = f"p{n}"
    while any(s["id"] == sid for s in spots):
        n += 1
        sid = f"p{n}"
    spots.append({"id": sid, "label": label, "by": "person", "struck": False, "gone": False,
                  "reach": {"kind": kind, "value": value}})
    _save(game, spots)
    return sid


def _change(game, sid, **fields):
    spots = load(game)
    for s in spots:
        if s["id"] == sid:
            s.update(fields)
            _save(game, spots)
            return True
    return False


def strike(game, sid):
    return _change(game, sid, struck=True)


def unstrike(game, sid):
    return _change(game, sid, struck=False)


def name(game, sid, label):
    return _change(game, sid, label=label)
