"""saveswap.py (the pretend game's): the same three commands as a real pack's save swapper.

    python saveswap.py start slot=N   game CLOSED: copies the save folder away, puts slot N's file over the newest one
    python saveswap.py end            game CLOSED: puts every file back and proves it by hash
    python saveswap.py status         says whether a swap is in force

The saves are in OPTIMIZER_PRETEND_SAVES; the copy and the marker beside them, in <saves>-swap/.
"""
import glob
import hashlib
import json
import os
import shutil
import sys

SAVES = os.environ["OPTIMIZER_PRETEND_SAVES"]
KEEP = SAVES.rstrip("\\/") + "-swap"
MARK = os.path.join(KEEP, "swap.json")


def hashes(d):
    out = {}
    for n in sorted(os.listdir(d)):
        p = os.path.join(d, n)
        if os.path.isfile(p):
            with open(p, "rb") as f:
                out[n] = hashlib.sha256(f.read()).hexdigest()
    return out


def running():
    return os.path.isfile(os.environ.get("OPTIMIZER_RUNNING_FILE", "") or "\0")


def start(slot):
    if os.path.exists(MARK):
        sys.exit("saveswap: a swap is already in force (run `end` first)")
    if running():
        sys.exit("saveswap: the game is running; close it first")
    src = os.path.join(SAVES, f"SaveGameData_{slot}.sav")
    if not os.path.exists(src):
        sys.exit(f"saveswap: slot {slot} has no file")
    newest = max(glob.glob(os.path.join(SAVES, "SaveGameData_*.sav")), key=os.path.getmtime)
    copy = os.path.join(KEEP, "saves")
    shutil.rmtree(copy, ignore_errors=True)
    shutil.copytree(SAVES, copy)
    before = hashes(SAVES)
    with open(MARK, "w") as f:
        json.dump({"copy": copy, "before": before, "slot": slot}, f)
    if os.path.abspath(src) != os.path.abspath(newest):
        shutil.copyfile(src, newest)
    print(f"saveswap: slot {slot} now sits over {os.path.basename(newest)} (the newest)")


def end():
    if not os.path.exists(MARK):
        sys.exit("saveswap: no swap in force")
    if running():
        sys.exit("saveswap: the game is running; close it first")
    with open(MARK) as f:
        m = json.load(f)
    for n in os.listdir(SAVES):
        if n not in m["before"]:
            os.remove(os.path.join(SAVES, n))
    for n in m["before"]:
        shutil.copy2(os.path.join(m["copy"], n), os.path.join(SAVES, n))
    if hashes(SAVES) != m["before"]:
        sys.exit("saveswap: NOT the same after putting back (the copy is kept)")
    os.remove(MARK)
    print(f"saveswap: every save put back, {len(m['before'])} files the same by hash")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "start":
        slot = next((int(a[5:]) for a in sys.argv[2:] if a.startswith("slot=")), 0)
        start(slot)
    elif cmd == "end":
        end()
    elif cmd == "status":
        print("saveswap: a swap is in force" if os.path.exists(MARK) else "saveswap: no swap in force")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
