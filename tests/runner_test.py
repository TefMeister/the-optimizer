"""runner_test.py - the runner and the job file: the AI is started with only two MCP servers (the toolbox and the
game's connector) and no built-in tools at all, its MCP config is written as it should be, and the job file names
only tools the toolbox really has. Nothing is started here. Exit 0 = pass."""
import json
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
fails = 0


def check(ok, what):
    global fails
    print(("  ok    " if ok else "FAIL: ") + what)
    fails += not ok


def main():
    t = tempfile.mkdtemp(prefix="optimizer-runner-")
    os.environ["OPTIMIZER_DIR"] = os.path.join(t, "optimizer")
    os.environ["OPTIMIZER_PACKS_DIR"] = os.path.join(HERE, "packs")
    os.environ["OPTIMIZER_PRETEND_HOME"] = os.path.join(t, "home")
    from runner import run
    from toolbox import tools

    # runner_allows_only_two_servers (Review Focus 1)
    cmd, prompt = run.build("pretend", "claude-code")
    allow = cmd[cmd.index("--allowedTools") + 1].split(",")
    check("--strict-mcp-config" in cmd, "runner_allows_only_two_servers: only the MCP servers in our config")
    check(sorted(allow) == ["mcp__optimizer__*", "mcp__pretend__*"],
          "runner_allows_only_two_servers: exactly the two allow patterns")
    check(cmd[cmd.index("--tools") + 1] == "", "runner_allows_only_two_servers: no built-in tool at all (no shell, "
                                                "no file writing, no web)")
    check("-p" in cmd and "stream-json" in cmd, "the agent runs on its own, its words kept as a stream")
    check("next_step" in prompt and "stop" in prompt, "the job file is the prompt")

    # runner_writes_mcp_config
    cfg_path = cmd[cmd.index("--mcp-config") + 1]
    cfg = json.load(open(cfg_path, encoding="utf-8"))
    srv = cfg["mcpServers"]["optimizer"]
    check(set(cfg["mcpServers"]) <= {"optimizer", "pretend"} and srv["args"][-2:] == ["--pack", "pretend"]
          and srv["args"][0].endswith(os.path.join("toolbox", "server.py")),
          "runner_writes_mcp_config: the toolbox for this game (and the connector when it has a server)")
    check(srv["env"].get("OPTIMIZER_DIR") == os.environ["OPTIMIZER_DIR"],
          "runner_writes_mcp_config: The Optimizer's own settings go to the toolbox")
    check(os.path.dirname(cfg_path) == os.path.join(os.environ["OPTIMIZER_DIR"], "pretend", "agent"),
          "runner_writes_mcp_config: in the game's own agent folder")
    headset_cmd, headset_prompt = run.build("pretend", "claude-code", headset=True)
    check("wears the real headset" in headset_prompt, "--headset tells the AI the person wears the headset")

    # the agents list
    agents = json.load(open(os.path.join(ROOT, "runner", "agents.json"), encoding="utf-8"))
    check(agents["claude-code"]["tested"] is True and agents["other"]["tested"] is False and agents["other"]["note"],
          "agents.json: Claude Code tested; other agents listed as untested, with what they need")

    # job_names_only_real_tools
    job = open(os.path.join(ROOT, "job", "job.md"), encoding="utf-8").read()
    named = set(re.findall(r"(?:[Cc]all|then) `([a-z_]+)`", job))     # "call `tool`": fields are not tools
    unknown = sorted(named - set(tools.TOOLS))
    check(not unknown, "job_names_only_real_tools" + (f": {unknown}" if unknown else ""))
    check({"preflight", "spots_find", "next_step", "apply_all", "result", "stop"} <= named,
          "the job file names the start, the loop, apply, the result and stop")

    print("runner_test: " + ("all passed" if not fails else f"{fails} FAILED"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
