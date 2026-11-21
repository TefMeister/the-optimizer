#!/usr/bin/env python3
"""run.py - starts the AI agent on the job, with only The Optimizer's toolbox and the game's connector.

    python runner/run.py <pack> [--agent claude-code] [--headset]     run the job (waits until the agent ends)
    python runner/run.py <pack> --show                                 print the command it would run, start nothing
    python runner/run.py <pack> --stop                                 the Stop button: end the agent, then quit the
                                                                       game by its own quit and put every save back
    python runner/run.py <pack> --undo                                 the Undo button: every file put back as it was

It writes <OPTIMIZER_DIR>/<game>/agent/mcp.json (the two servers), starts the agent in that folder with job/job.md as
its prompt, keeps everything the agent says in agent.log, and records the agent's process in run.json (the window
reads it to know a run is going, and to stop it).
"""
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from engine import pack as P  # noqa: E402
from engine import settings as C  # noqa: E402

JOB = os.path.join(ROOT, "job", "job.md")
SERVER = os.path.join(ROOT, "toolbox", "server.py")
HEADSET_LINE = "\n\n**This run: the person wears the real headset** (call `launch_game` with headset true).\n"
SIM_LINE = "\n\n**This run: nobody wears the headset**; the pretend headset is used.\n"


def agents():
    with open(os.path.join(HERE, "agents.json"), encoding="utf-8") as f:
        return json.load(f)


def agent_dir(game):
    return os.path.join(C.game_dir(game), "agent")


def write_mcp_config(pack):
    d = agent_dir(pack["name"])
    os.makedirs(d, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if k.startswith("OPTIMIZER_")}
    env.setdefault("OPTIMIZER_DIR", C.base_dir())
    servers = {"optimizer": {"command": sys.executable, "args": [SERVER, "--pack", pack["name"]], "env": env}}
    con = pack.get("connector") or {}
    cmd = os.path.expandvars(con.get("mcp_command") or "")
    if con.get("mcp_name") and cmd and os.path.isfile(cmd):
        servers[con["mcp_name"]] = {"command": cmd, "args": con.get("mcp_args") or []}
    path = os.path.join(d, "mcp.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"mcpServers": servers}, f, indent=1)
    return path


def allow_patterns(pack):
    out = ["mcp__optimizer__*"]
    con = pack.get("connector") or {}
    name = con.get("mcp_name")
    if name:
        only = con.get("allow_tools")      # the connector tools the way into play needs; none named = all of them
        out += [f"mcp__{name}__{t}" for t in only] if only else [f"mcp__{name}__*"]
    return out


def build(pack_name, agent="claude-code", headset=False):
    """(the command, the prompt) for one run; nothing is started."""
    pack = P.load(pack_name)
    a = agents()[agent]
    if not a.get("cmd"):
        raise SystemExit(f"run: '{agent}' has no command line yet ({a.get('note', '')})")
    program = shutil.which(a.get("program", "")) or a.get("program", "")
    rep = {"{program}": program, "{mcp_config}": write_mcp_config(pack), "{allow}": ",".join(allow_patterns(pack))}
    cmd = [rep.get(x, x) for x in a["cmd"]]
    with open(JOB, encoding="utf-8") as f:
        prompt = f.read() + (HEADSET_LINE if headset else SIM_LINE)
    return cmd, prompt


def _run_file(game):
    return os.path.join(agent_dir(game), "run.json")


def run(pack_name, agent, headset):
    cmd, prompt = build(pack_name, agent, headset)
    d = agent_dir(pack_name)
    log = open(os.path.join(d, "agent.log"), "a", encoding="utf-8")
    log.write(f"\n==== {time.strftime('%Y-%m-%d %H:%M:%S')} {agent} {'headset' if headset else 'pretend headset'}\n")
    log.flush()
    p = subprocess.Popen(cmd, cwd=d, stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT, text=True,
                         encoding="utf-8")
    with open(_run_file(pack_name), "w", encoding="utf-8") as f:
        json.dump({"pid": p.pid, "agent": agent, "headset": headset, "started": time.time(), "runner": os.getpid()}, f)
    p.stdin.write(prompt)
    p.stdin.close()
    code = p.wait()
    log.write(f"\n==== the agent ended ({code})\n")
    log.close()
    try:
        os.remove(_run_file(pack_name))
    except OSError:
        pass
    return code


def stop(pack_name):
    """The Stop button: the agent is ended first (it is our own helper, not the game), then the toolbox's own stop
    quits the game by its own quit and puts every save back."""
    try:
        with open(_run_file(pack_name), encoding="utf-8") as f:
            r = json.load(f)
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(r["pid"]), "/T", "/F"], capture_output=True)
        else:
            os.kill(r["pid"], 15)
        os.remove(_run_file(pack_name))
    except (OSError, ValueError, KeyError):
        pass
    from toolbox import tools
    res, _ = tools.call(tools.Box(pack_name), "stop", {"why": "the Stop button"})
    print(res["say"])
    return 0


def main(argv):
    if not argv or argv[0].startswith("-"):
        print(__doc__.strip())
        return 2
    pack = argv[0]
    agent = argv[argv.index("--agent") + 1] if "--agent" in argv else "claude-code"
    if "--stop" in argv:
        return stop(pack)
    if "--undo" in argv:
        from engine import finish as F
        for line in F.undo(pack):
            print(line)
        return 0
    if "--show" in argv:
        cmd, _ = build(pack, agent, "--headset" in argv)
        print(" ".join(f'"{c}"' if (" " in c or not c) else c for c in cmd))
        return 0
    return run(pack, agent, "--headset" in argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
