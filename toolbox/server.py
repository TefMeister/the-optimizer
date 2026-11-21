#!/usr/bin/env python3
"""server.py - The Optimizer's toolbox as an MCP server (stdio; JSON-RPC 2.0, one message per line, written by hand so
nothing needs installing beyond Python).

    python toolbox/server.py --pack <game pack>

One server serves one game. Methods: initialize, notifications/initialized, ping, tools/list, tools/call. Every tool
returns one text block holding JSON with a "say" line in plain words; a refusal is an error result (isError) whose
"say" is the reason. Nothing is ever written to stdout but the protocol's own messages.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from engine import settings as C  # noqa: E402
from toolbox import tools  # noqa: E402

PROTOCOL = "2025-06-18"
VERSION = "0.1.0"


def send(msg):
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def reply(mid, result=None, error=None):
    m = {"jsonrpc": "2.0", "id": mid}
    if error:
        m["error"] = error
    else:
        m["result"] = result
    send(m)


def main(argv):
    if "--pack" not in argv or argv.index("--pack") + 1 >= len(argv):
        sys.stderr.write("usage: server.py --pack <game pack>\n")
        return 2
    for stream in (sys.stdin, sys.stdout):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    box = tools.Box(argv[argv.index("--pack") + 1])
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            reply(None, error={"code": -32700, "message": "not JSON"})
            continue
        mid, method = msg.get("id"), msg.get("method", "")
        params = msg.get("params") or {}
        if mid is None:                       # a notification: no answer
            continue
        if method == "initialize":
            reply(mid, {"protocolVersion": params.get("protocolVersion") or PROTOCOL,
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "optimizer", "version": VERSION},
                        "instructions": "The Optimizer's toolbox for one game. Follow job/job.md: call next_step and "
                                        "do what it says, one tool at a time."})
        elif method == "ping":
            reply(mid, {})
        elif method == "tools/list":
            reply(mid, {"tools": [{"name": n, "description": d, "inputSchema": s}
                                  for n, (d, s) in tools.TOOLS.items()]})
        elif method == "tools/call":
            res, err = tools.call(box, params.get("name", ""), params.get("arguments") or {})
            reply(mid, {"content": [{"type": "text", "text": json.dumps(res)}], "isError": bool(err)})
        else:
            reply(mid, error={"code": -32601, "message": f"no method {method}"})
    return 0


if __name__ == "__main__":
    C.base_dir()
    sys.exit(main(sys.argv[1:]))
