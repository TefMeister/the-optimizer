"""pack_test.py - game packs: the shipped Silent Hill 2 pack is complete, a pack missing its quit is told so in plain
words, a setting that lives only in the running game must be marked safe to change live, and the window's list of
packs. Exit 0 = pass."""
import contextlib
import copy
import io
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
fails = 0


def check(ok, what):
    global fails
    print(("  ok    " if ok else "FAIL: ") + what)
    fails += not ok


def main():
    t = tempfile.mkdtemp(prefix="optimizer-pack-")
    os.environ["OPTIMIZER_DIR"] = os.path.join(t, "optimizer")
    from engine import pack as P
    from engine import cli

    # sh2_pack_complete
    check("silent-hill-2" in P.list_packs(), "sh2_pack_complete: the Silent Hill 2 pack ships")
    sh2 = P.load("silent-hill-2")
    problems = P.check(sh2)
    check(problems == [], "sh2_pack_complete: its check finds nothing missing" + (f" ({problems})" if problems else ""))
    knobs = {k["id"]: k for k in sh2["settings"]["knobs"]}
    check(set(knobs) == {"rt_reflections", "shadow_res", "ao", "local_exposure", "dlss_level", "xr_scale"},
          "sh2_pack_complete: the six agreed settings, nothing else")
    check(not any("ScreenPercentage" in k.get("key", "") or k.get("key", "").startswith("sg.") for k in knobs.values()),
          "sh2_pack_complete: no r.ScreenPercentage, no sg.* groups")
    check(all("keep" in k for k in knobs.values()) and knobs["rt_reflections"]["keep"] is None
          and knobs["dlss_level"]["keep"], "sh2_pack_complete: each setting says where it lasts (or that it does not)")
    check(os.path.isfile(os.path.join(P.pack_dir("silent-hill-2"), sh2["swap_tool"])),
          "sh2_pack_complete: the save swapper ships inside the pack")

    # pack_missing_quit_is_named
    noquit = copy.deepcopy(sh2)
    del noquit["quit"]
    check(P.check(noquit) == ["no way to quit the game by its own means"],
          "pack_missing_quit_is_named: exactly one problem, in plain words")

    # no_live_knob_without_safe
    bad = copy.deepcopy(sh2)
    for k in bad["settings"]["knobs"]:
        if k["id"] == "ao":
            k.pop("live_safe")
    probs = P.check(bad)
    check(len(probs) == 1 and "ao" in probs[0] and "safe" in probs[0],
          "no_live_knob_without_safe: a live-only setting not marked safe live is a problem")

    # the window's list (engine.cli packs --json)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = cli.main(["packs", "--json"])
    rows = json.loads(out.getvalue())
    sh2_row = [r for r in rows if r["name"] == "silent-hill-2"]
    check(code == 0 and sh2_row and sh2_row[0]["label"] and "installed" in sh2_row[0] and sh2_row[0]["complete"],
          "packs --json lists each pack with its label, whether the game is on this PC, and whether it is complete")

    print("pack_test: " + ("all passed" if not fails else f"{fails} FAILED"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
