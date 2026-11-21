"""dry_run.py - the whole job, end to end, by a real AI agent (Claude Code) against the pretend game: nothing real is
launched or changed (a temp folder, a pretend registry for the meter, the pretend game's own connector).

    python tests/dry_run.py [--agent claude-code]

Passes when: result.txt is written, the pretend game was quit through its own quit (and is not running), every save
is back as it was, and the agent's log shows no tool outside The Optimizer's toolbox and the game's connector.
It spends tokens on the account the agent is signed in with (one short tour of two spots). Exit 0 = pass."""
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def sha_dir(d):
    out = {}
    for n in sorted(os.listdir(d)):
        with open(os.path.join(d, n), "rb") as f:
            out[n] = hashlib.sha256(f.read()).hexdigest()
    return out


def main(argv):
    agent = argv[argv.index("--agent") + 1] if "--agent" in argv else "claude-code"
    t = tempfile.mkdtemp(prefix="optimizer-dry-")
    home, saves, dist = (os.path.join(t, n) for n in ("home", "saves", "dist"))
    for d in (home, saves, dist, os.path.join(home, "vr")):
        os.makedirs(d)
    shutil.copy(os.path.join(HERE, "packs", "pretend", "pretend_game.py"), home)
    open(os.path.join(home, "pretend_game.exe"), "wb").close()
    open(os.path.join(home, "vr", "backend.dll"), "wb").close()
    with open(os.path.join(home, "settings.ini"), "w") as f:
        f.write("Shadow=1\n")
    for i in range(2):
        p = os.path.join(saves, f"SaveGameData_{i}.sav")
        with open(p, "wb") as f:
            f.write(b"slot %d" % i)
        os.utime(p, (1000 + i, 1000 + i))
    for n in ("lanes_tune_meter.dll", "lanes_tune_meter.json"):
        open(os.path.join(dist, n), "w").close()
    before = sha_dir(saves)
    env = dict(os.environ)
    env.update({"OPTIMIZER_DIR": os.path.join(t, "optimizer"), "OPTIMIZER_PACKS_DIR": os.path.join(HERE, "packs"),
                "OPTIMIZER_PRETEND_HOME": home, "OPTIMIZER_PRETEND_SAVES": saves,
                "OPTIMIZER_RUNNING_FILE": os.path.join(t, "running"),
                "OPTIMIZER_UEVR_BASE": f"http://127.0.0.1:{free_port()}", "OPTIMIZER_SIM_DATA": os.path.join(t, "sim"),
                "OPTIMIZER_NO_GPU": "1", "OPTIMIZER_LANES_CONF": os.path.join(t, "lanes.conf"),
                "OPTIMIZER_FAKEREG": os.path.join(t, "reg.json"), "OPTIMIZER_METER_DIST": dist,
                "OPTIMIZER_QUIT_WAIT_S": "20", "OPTIMIZER_LOOK_STEP_S": "0.5"})
    print(f"dry run in {t}", flush=True)
    code = subprocess.call([sys.executable, os.path.join(ROOT, "runner", "run.py"), "pretend", "--agent", agent],
                           env=env)
    gdir = os.path.join(t, "optimizer", "pretend")
    log = open(os.path.join(gdir, "agent", "agent.log"), encoding="utf-8", errors="replace").read()
    used = set()
    for line in log.splitlines():
        try:
            m = json.loads(line)
        except ValueError:
            continue
        for c in ((m.get("message") or {}).get("content") or []) if isinstance(m, dict) else []:
            if isinstance(c, dict) and c.get("type") == "tool_use":
                used.add(c.get("name"))
    outside = sorted(u for u in used if not (u.startswith("mcp__optimizer__") or u.startswith("mcp__pretend__")))
    box_log = open(os.path.join(gdir, "toolbox.log"), encoding="utf-8").read() if os.path.isfile(
        os.path.join(gdir, "toolbox.log")) else ""
    checks = [
        (code == 0, f"the agent ended normally (exit {code})"),
        (os.path.isfile(os.path.join(gdir, "result.txt")), "result.txt written"),
        ("quit: the game's own quit" in box_log and not os.path.exists(env["OPTIMIZER_RUNNING_FILE"]),
         "the pretend game was quit by its own quit and is not running"),
        ("taskkill" not in box_log.lower(), "nothing was killed"),
        (sha_dir(saves) == before, "every save is back as it was"),
        (not outside and used, "no tool outside the two servers" + (f": {outside}" if outside else "")),
    ]
    for ok, what in checks:
        print(("  ok    " if ok else "FAIL: ") + what)
    print("tools used: " + ", ".join(sorted(u.split("__")[-1] for u in used)))
    if os.path.isfile(os.path.join(gdir, "result.txt")):
        print(open(os.path.join(gdir, "result.txt"), encoding="utf-8").read())
    bad = sum(not ok for ok, _ in checks)
    print("dry_run: " + ("all passed" if not bad else f"{bad} FAILED"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
