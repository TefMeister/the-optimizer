"""toolbox_test.py - The Optimizer's toolbox (the MCP server the AI uses), driven over its pipes the way an AI agent
drives it, with the pretend game (tests/packs/pretend) in a temp folder. Checks the safety rules that live in the tools:
no launch without the VR files or while a session holds the game, no save swap while the game runs, a swap left in
force by a stop is put back first thing, and the game is quit by its own quit, never killed. Exit 0 = pass."""
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SERVER = os.path.join(ROOT, "toolbox", "server.py")
fails = 0
EXPECTED = {"preflight", "launch_game", "quit_game", "game_state", "spots_find", "next_step", "spot_reach",
            "spot_arrived", "settle_wait", "look_and_measure", "setting_set", "godmode", "report_crash",
            "report_death", "connector_cost", "apply_all", "result", "stop", "progress"}


def check(ok, what):
    global fails
    print(("  ok    " if ok else "FAIL: ") + what)
    fails += not ok


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class Box:
    """One toolbox server over pipes: newline-delimited JSON-RPC, as MCP's stdio transport."""
    def __init__(self, env):
        self.p = subprocess.Popen([sys.executable, SERVER, "--pack", "pretend"], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, text=True,
                                  encoding="utf-8")
        self.n = 0
        self.init = self.rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                            "clientInfo": {"name": "toolbox_test", "version": "0"}})
        self.p.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        self.p.stdin.flush()

    def rpc(self, method, params=None):
        self.n += 1
        self.p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": self.n, "method": method, "params": params or {}}) + "\n")
        self.p.stdin.flush()
        line = self.p.stdout.readline()
        if not line:
            raise AssertionError("the toolbox closed its pipe: " + self.p.stderr.read()[-2000:])
        msg = json.loads(line)
        assert msg.get("id") == self.n, msg
        return msg

    def call(self, tool, **args):
        msg = self.rpc("tools/call", {"name": tool, "arguments": args})
        res = msg["result"]
        return json.loads(res["content"][0]["text"]), res.get("isError", False)

    def close(self):
        self.p.stdin.close()
        self.p.wait(timeout=20)


def sha_dir(d):
    out = {}
    for n in sorted(os.listdir(d)):
        with open(os.path.join(d, n), "rb") as f:
            out[n] = hashlib.sha256(f.read()).hexdigest()
    return out


def setup():
    t = tempfile.mkdtemp(prefix="optimizer-box-")
    home = os.path.join(t, "home")
    saves = os.path.join(t, "saves")
    os.makedirs(home)
    os.makedirs(saves)
    shutil.copy(os.path.join(HERE, "packs", "pretend", "pretend_game.py"), home)
    open(os.path.join(home, "pretend_game.exe"), "wb").close()
    for i in range(3):
        with open(os.path.join(saves, f"SaveGameData_{i}.sav"), "wb") as f:
            f.write(b"slot %d" % i)
        os.utime(os.path.join(saves, f"SaveGameData_{i}.sav"), (1000 + i, 1000 + i))
    dist = os.path.join(t, "dist")
    os.makedirs(dist)
    for n in ("lanes_tune_meter.dll", "lanes_tune_meter.json"):
        open(os.path.join(dist, n), "w").close()
    env = dict(os.environ)
    env.update({"OPTIMIZER_DIR": os.path.join(t, "optimizer"), "OPTIMIZER_PACKS_DIR": os.path.join(HERE, "packs"),
                "OPTIMIZER_PRETEND_HOME": home, "OPTIMIZER_PRETEND_SAVES": saves,
                "OPTIMIZER_RUNNING_FILE": os.path.join(t, "running"),
                "OPTIMIZER_UEVR_BASE": f"http://127.0.0.1:{free_port()}", "OPTIMIZER_SIM_DATA": os.path.join(t, "sim"),
                "OPTIMIZER_NO_GPU": "1", "OPTIMIZER_LANES_CONF": os.path.join(t, "lanes.conf"),
                "OPTIMIZER_FAKEREG": os.path.join(t, "reg.json"), "OPTIMIZER_METER_DIST": dist,
                "OPTIMIZER_QUIT_WAIT_S": "20", "PYTHONIOENCODING": "utf-8"})
    env.pop("OPTIMIZER_FAKE_RUNNING", None)
    return t, home, saves, env


def vr_files(home):
    os.makedirs(os.path.join(home, "vr"), exist_ok=True)
    open(os.path.join(home, "vr", "backend.dll"), "wb").close()


def main():
    # lists_every_tool
    t, home, saves, env = setup()
    box = Box(env)
    names = {tl["name"] for tl in box.rpc("tools/list")["result"]["tools"]}
    check(box.init["result"]["serverInfo"]["name"] == "optimizer", "the server calls itself 'optimizer'")
    check(names == EXPECTED, "lists_every_tool" + ("" if names == EXPECTED else f": {sorted(names ^ EXPECTED)}"))

    # launch_refused_without_vr_files
    pre, _ = box.call("preflight")
    res, err = box.call("launch_game")
    check(not pre["ok"] and any("VR" in p for p in pre["problems"]), "launch_refused_without_vr_files: preflight says so")
    check(err and not res.get("launched") and not os.path.exists(env["OPTIMIZER_RUNNING_FILE"]),
          "launch_refused_without_vr_files: launch refused, nothing started")

    # launch_refused_when_claimed
    vr_files(home)
    os.makedirs(env["OPTIMIZER_DIR"], exist_ok=True)
    with open(os.path.join(env["OPTIMIZER_DIR"], "claim.json"), "w") as f:
        json.dump({"game": "pretend", "by": "a modding session"}, f)
    pre, _ = box.call("preflight")
    res, err = box.call("launch_game")
    check(err and "a modding session" in res["say"] and not os.path.exists(env["OPTIMIZER_RUNNING_FILE"]),
          "launch_refused_when_claimed: a claimed game is not launched")
    os.remove(os.path.join(env["OPTIMIZER_DIR"], "claim.json"))

    # swap_refused_while_running
    box.call("spots_find")
    open(env["OPTIMIZER_RUNNING_FILE"], "w").close()
    st, _ = box.call("next_step")
    res, err = box.call("spot_reach")
    check(st["do"] == "reach" and err and "running" in res["say"]
          and not os.path.exists(saves.rstrip("\\/") + "-swap" + os.sep + "swap.json"),
          "swap_refused_while_running: no save swap while the game runs")
    os.remove(env["OPTIMIZER_RUNNING_FILE"])

    # quit_never_kills
    pre, _ = box.call("preflight")
    check(pre["ok"], "preflight passes with the VR files in place" + ("" if pre["ok"] else f": {pre['problems']}"))
    res, err = box.call("launch_game")
    for _ in range(100):
        if os.path.exists(env["OPTIMIZER_RUNNING_FILE"]):
            break
        time.sleep(0.1)
    check(not err and os.path.exists(env["OPTIMIZER_RUNNING_FILE"]), "launch_game starts the game")
    res, err = box.call("quit_game")
    log = open(os.path.join(env["OPTIMIZER_DIR"], "pretend", "toolbox.log"), encoding="utf-8").read()
    cmds = open(os.path.join(home, "pretend-commands.log"), encoding="utf-8").read().split()
    check(not err and not os.path.exists(env["OPTIMIZER_RUNNING_FILE"]) and "quit" in cmds,
          "quit_never_kills: the game quit through its own quit")
    check("taskkill" not in log.lower() and "terminate" not in log.lower(), "quit_never_kills: no kill was ever run")
    box.close()

    # stop_mid_swap_restores_first
    before = sha_dir(saves)
    subprocess.run([sys.executable, os.path.join(HERE, "packs", "pretend", "saveswap.py"), "start", "slot=0"],
                   env=env, check=True, capture_output=True)
    check(sha_dir(saves) != before, "(a swap is in force: the newest slot now holds slot 0)")
    box = Box(env)
    st, _ = box.call("game_state")
    check(sha_dir(saves) == before and not os.path.exists(os.path.join(saves + "-swap", "swap.json")),
          "stop_mid_swap_restores_first: the next start of the toolbox put every save back first")
    check("put back" in json.dumps(st), "stop_mid_swap_restores_first: and says so")
    box.close()

    print("toolbox_test: " + ("all passed" if not fails else f"{fails} FAILED"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
