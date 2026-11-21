"""tools.py - the toolbox's tools: one per step of the job (job/job.md), each a thin call into the engine, each
returning {"say": <plain words>, ...numbers}. The rules that protect the PC live here, not in the AI's judgement:
  - launch_game refuses without a passing preflight, without the VR files, while a session holds the game, while a
    save swap is still in force from a stop, or while the game already runs;
  - spot_reach of a save slot refuses while the game runs;
  - setting_set sends a change live only to a setting marked safe live, and writes a restart-only one only with the
    game closed;
  - godmode only with the pack's own route, once per spot;
  - quit_game uses the game's own quit and never kills;
  - apply_all only with the game closed.
A refusal comes back as an error result with the reason in "say": the job file says what to do with each.
"""
import json
import os
import time

from engine import finish as F
from engine import knobs as K
from engine import pack as P
from engine import read as R
from engine import settings as C
from engine import spots as SP
from engine import tour as T
from engine import look as L
from toolbox import game as G


class Refused(Exception):
    pass


class Box:
    def __init__(self, pack_name):
        self.pack = P.load(pack_name)
        self.game = self.pack["name"]
        self.exe = P.exe_path(self.pack) or self.pack["exe"]
        self.startup = self._restore_swap_first()

    # ---- small helpers -----------------------------------------------------------------------------------------
    def _running(self):
        return C.game_running(self.exe)

    def _tour(self):
        try:
            return T.load(self.game)
        except SystemExit:
            return None

    def _knob(self, kid):
        for k in (self.pack.get("settings") or {}).get("knobs", []):
            if k["id"] == kid:
                return k
        raise Refused(f"there is no setting '{kid}' in this game's pack")

    def _restore_swap_first(self):
        """At the toolbox's start: a save swap left in force (a stop, a crash) is put back before anything else."""
        if not self.pack.get("swap_tool") or not G.swap_in_force(self.pack):
            return None
        if self._running():
            return ("a save swap is still in force and the game is running: quit_game first, the saves are put back "
                    "as soon as it has closed")
        ok, said = G.swap_end(self.pack)
        G.log(self.game, f"startup: a swap was in force; put back: {ok} ({said})")
        return ("a save swap was still in force from the last run: every save was put back first (" + said + ")"
                if ok else "a save swap is in force and could NOT be put back: " + said)

    def _after_quit(self):
        """Once the game has closed: any save swap is put back at once (saves are out of place only while it runs)."""
        if self.pack.get("swap_tool") and G.swap_in_force(self.pack):
            ok, said = G.swap_end(self.pack)
            return said if ok else "the saves could NOT be put back: " + said
        return None

    # ---- the tools ---------------------------------------------------------------------------------------------
    def preflight(self, headset=False):
        problems, notes = list(P.check(self.pack)), []
        exe = P.exe_path(self.pack)
        if not exe:
            problems.append("the game is not found on this PC")
        where = G.launcher(self.pack)
        if not where:
            problems.append(f"the launcher ({self.pack.get('launch', {}).get('program')}) is not found")
        else:
            miss = G.missing_vr_files(self.pack, where)
            if miss:
                problems.append("the VR files are not beside the launcher: " + ", ".join(miss))
        who = G.claimed_by(self.pack)
        if who:
            problems.append(f"the game is held by {who}: The Optimizer waits until it is let go")
        problems += self._meter_on()
        if headset:
            notes.append("you wear the headset for this run")
        elif "--sim" in (self.pack.get("launch") or {}).get("args", []):
            notes.append("the pretend headset is started by the game's launcher (--sim)")
        else:
            notes.append("the pretend headset: start the OpenXR Simulator as the active runtime before launching")
        notes.append(f"the pretend headset's picture size ({self.pack['picture']['w']} x {self.pack['picture']['h']}) "
                     "is not set by The Optimizer yet: it measures at the size the simulator is set to")
        notes.append("the collector: Lanes shelves the meter's files by itself when Lanes is installed")
        t = self._tour()
        if t and t.get("phase") == "done" and t.get("applied") and not t.get("check_lines"):
            notes += F.check_applied(self.game)
        ok = not problems
        with open(os.path.join(C.game_dir(self.game), "preflight.json"), "w", encoding="utf-8") as f:
            json.dump({"ok": ok, "when": time.time(), "problems": problems}, f)
        say = ("everything is in place" if ok else "NOT ready: " + "; ".join(problems))
        return {"ok": ok, "problems": problems, "notes": notes, "say": say}

    def _meter_on(self):
        from engine import cli
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.cmd_meter(["on", self.exe])
        return [] if code == 0 else ["the frame meter: " + out.getvalue().strip()]

    def launch_game(self, headset=False):
        try:
            with open(os.path.join(C.game_dir(self.game), "preflight.json"), encoding="utf-8") as f:
                pre = json.load(f)
        except (OSError, ValueError):
            pre = {"ok": False, "when": 0, "problems": ["no preflight yet"]}
        who = G.claimed_by(self.pack)
        if who:
            raise Refused(f"the game is held by {who}: not launched")
        if not pre["ok"] or time.time() - pre["when"] > C.PREFLIGHT_FRESH_S:
            raise Refused("run preflight first (and fix what it says): " + "; ".join(pre.get("problems") or []))
        where = G.launcher(self.pack)
        miss = G.missing_vr_files(self.pack, where) if where else ["the launcher"]
        if miss:
            raise Refused("the VR files are not beside the launcher: " + ", ".join(miss) + ". Not launched")
        if self._running():
            raise Refused("the game is already running")
        if self.startup and "could NOT" in self.startup:
            raise Refused(self.startup)
        G.launch(self.pack, where, headset)
        up = G.wait_running(self.pack, True, C.LAUNCH_WAIT_S)
        return {"launched": up, "say": "the game is starting: walk to_play, then spot_arrived" if up
                else "the game did not start (a failed launch)", "to_play": self.pack.get("to_play")}

    def quit_game(self):
        ok, said = G.quit_game(self.pack)
        back = self._after_quit() if ok else None
        if not ok:
            raise Refused(said)
        if self._tour():
            T.left(self.game)
        return {"closed": True, "say": said + (f"; {back}" if back else "")}

    def game_state(self):
        running = self._running()
        crash = G.crash_seen(self.pack) if not running else None
        say = ("the game is running" if running else "the game is not running") + (
            f"; it crashed (the log says: {crash})" if crash else "")
        if self.startup:
            say += "; " + self.startup
        return {"running": running, "crashed": bool(crash), "connector": running and G.connector_up(self.pack),
                "say": say}

    def spots_find(self):
        build = None
        if os.path.isfile(self.exe):
            st = os.stat(self.exe)
            build = f"{st.st_size}-{int(st.st_mtime)}"
        T.begin(self.game, self.pack, build=build, exe=self.exe)
        spots = SP.active(self.game)
        return {"spots": [{"id": s["id"], "label": s["label"]} for s in spots],
                "say": f"{len(spots)} spot(s) to visit: " + ", ".join(s["label"] for s in spots)}

    def next_step(self):
        return T.next_step(self.game)

    def spot_reach(self):
        tour = T.load(self.game)
        if not tour.get("at"):
            raise Refused("there is no spot to reach now: call next_step")
        spot = SP.get(self.game, tour["at"])
        reach = spot["reach"]
        if reach["kind"] == "save_slot":
            if self._running():
                raise Refused("a save slot is swapped in only with the game closed, and the game is running: "
                              "quit_game first")
            ok, said = G.swap_start(self.pack, reach["value"])
            if not ok:
                raise Refused("the save swap did not work: " + said)
            return {"say": f"{spot['label']} is in place ({said}). Now: launch_game, walk to_play, spot_arrived",
                    "to_play": self.pack.get("to_play")}
        if reach["kind"] in ("console", "level_jump"):
            if not self._running():
                raise Refused("a console jump needs the game running: launch_game first")
            ok, said = G.console(self.game, str(reach["value"]))
            if not ok:
                raise Refused(said)
            return {"say": f"sent '{reach['value']}': when it has loaded, spot_arrived"}
        raise Refused(f"a '{reach['kind']}' spot cannot be reached by The Optimizer yet")

    def spot_arrived(self, label=None):
        T.arrived(self.game, label)
        tour = T.load(self.game)
        sent = []
        for k in tour["knobs"]:                        # live-only values are lost at every start: send them again
            i = tour["levels"].get(k["id"])
            if i is not None and K.live_ok(k) and k.get("keep") is None:
                ok, _ = K.push_live(k, k["steps"][i])
                sent.append(f"{k['label']} {k['steps'][i]}" + ("" if ok else " (not sent)"))
        return {"say": "arrived" + (f"; sent again: {', '.join(sent)}" if sent else "")}

    def settle_wait(self):
        tour = T.load(self.game)
        stem = os.path.splitext(os.path.basename(self.exe))[0]
        t0, need = time.time(), float(tour.get("settle") or 0)
        # Steady = the frame rate stopped moving (each live reading within SETTLE_FPS_SHARE of the one before), not
        # "no missed frames": the meter counts a miss against the headset's own period, so on a 90 Hz pretend headset
        # a game at 65 a second misses every few frames for good and the old test always ran the full SETTLE_MAX_S
        # (found 2026-11-21, the first SH2 run).
        steady_since, last_fps = None, None
        while time.time() - t0 < C.SETTLE_MAX_S:
            v = R.read_live(stem)
            fresh = v is not None and v.get("_age_s", 99) < 3
            fps = v.get("fps") if fresh else None
            if fps and last_fps and abs(fps - last_fps) <= C.SETTLE_FPS_SHARE * last_fps:
                steady_since = steady_since or time.time()
                if time.time() - steady_since >= need:
                    break
            elif fps:
                steady_since = None
            if fps:
                last_fps = fps
            time.sleep(0.25)
        T.settled(self.game)
        return {"say": f"steady after {time.time() - t0:.0f} s"}

    def look_and_measure(self):
        tour = T.load(self.game)
        if not self._running():
            raise Refused("the game is not running: report_crash if it crashed, else launch_game")
        T.marker(self.game, "look_start")
        holder = {}

        def during():
            holder["s"] = L.look_around(headset=tour.get("headset", False))
            return holder["s"]
        rows, gpu, why = R.measure_window(self.exe, None, during=during)
        T.marker(self.game, "look_end")
        if why and not rows:
            raise Refused(why)
        v = T.measured(self.game, rows, gpu)
        last = T.load(self.game)["spots"].get(tour["at"], {}).get("last") or {}
        from engine import decide as D
        return {"verdict": v, "summary": last.get("summary"),
                "say": D.plain(last.get("summary"), gpu, v) if last else f"measured: {v['result']}"}

    def setting_set(self, knob, to):
        k = self._knob(knob)
        tour = T.load(self.game)
        if K.step_index(k, to) is None or str(to) not in [str(s) for s in k["steps"]]:
            raise Refused(f"'{to}' is not one of {k['label']}'s steps: {', '.join(map(str, k['steps']))}")
        if K.live_ok(k):
            if not self._running():
                raise Refused(f"{k['label']} is changed live, and the game is not running")
            ok, said = K.push_live(k, to)
            if not ok:
                raise Refused(said)
            how = "changed live"
        else:
            if self._running():
                raise Refused(f"{k['label']} is not safe to change live: quit_game first, then set it")
            if k.get("kind") == "live_cvar":
                raise Refused(f"{k['label']} lives only in the running game and is not safe live: it cannot be set")
            K.set_value(k, to, {"exe": tour["exe"]}, self.game)
            how = "written for the next start"
        T.changed(self.game, knob, to)
        return {"say": f"{k['label']} -> {K.shown(k, to)} ({how})"}

    def godmode(self):
        gm = self.pack.get("godmode")
        if not gm:
            raise Refused("this game's pack has no god mode")
        tour = T.load(self.game)
        if tour["spots"].get(tour["at"], {}).get("god"):
            raise Refused("god mode is already on at this spot")
        ok, said = G.console(self.game, gm["console"])
        if not ok:
            raise Refused(said)
        T.godmode_on(self.game)
        return {"say": "god mode on"}

    def report_crash(self):
        T.crashed(self.game)
        back = self._after_quit() if not self._running() else None
        return {"say": "noted: the game crashed" + (f"; {back}" if back else "")}

    def report_death(self):
        T.died(self.game)
        return {"say": "noted: the player died"}

    def connector_cost(self, with_ms=None, without_ms=None):
        if with_ms is None or without_ms is None:
            T.cost(self.game, 0.0, 0.0)
            tour = T.load(self.game)
            tour["connector_say"] = ("the connector's own cost was not measured in this version (a run without it "
                                     "has no connector to drive the menus): nothing subtracted")
            T.save(self.game, tour)
            return {"say": tour["connector_say"]}
        T.cost(self.game, float(with_ms), float(without_ms))
        return {"say": T.load(self.game)["connector_say"]}

    def apply_all(self):
        if self._running():
            raise Refused("the settings are written only with the game closed: quit_game first")
        lines = F.apply(self.game)
        return {"lines": lines, "say": "; ".join(lines)}

    def result(self):
        lines = F.result(self.game)
        return {"lines": lines, "file": os.path.join(C.game_dir(self.game), "result.txt"),
                "say": "the result is written"}

    def stop(self, why="stopped"):
        said = []
        if self._running():
            ok, s = G.quit_game(self.pack)
            said.append(s)
        back = self._after_quit()
        if back:
            said.append(back)
        if self._tour():
            T.stop(self.game, why)
            F.result(self.game)
        return {"say": "stopped (" + why + ")" + ("; " + "; ".join(said) if said else "")}

    def progress(self, doing=""):
        write_progress(self, doing)
        return {"say": "noted"}

    def wait(self, seconds=5):
        """A plain pause while the game loads: the AI has no clock of its own (added 2026-11-21, the first SH2 run:
        the pack's to_play waits up to two minutes, which without this meant calling the connector over and over)."""
        try:
            s = float(seconds)
        except (TypeError, ValueError):
            raise Refused("seconds must be a number")
        s = max(1.0, min(s, WAIT_MAX_S))
        time.sleep(s)
        return {"say": f"waited {s:g} s; the game is {'running' if self._running() else 'NOT running'}",
                "running": self._running()}


def write_progress(box, doing="", last=""):
    """What the window shows: <game>/progress.json, rewritten after every tool call."""
    tour = box._tour() or {}
    active = SP.active(box.game) if tour else []
    done = [s["id"] for s in active if tour.get("spots", {}).get(s["id"], {}).get("status", "todo") != "todo"]
    at = tour.get("at")
    d = {"game": box.game, "label": box.pack.get("label"), "phase": tour.get("phase", "starting"),
         "round": tour.get("round", 0), "at": at, "at_label": (SP.get(box.game, at) or {}).get("label") if at else None,
         "step": tour.get("step"), "spots_total": len(active), "spots_done": len(done), "doing": doing,
         "last": last, "when": time.strftime("%Y-%m-%d %H:%M:%S"), "toolbox_pid": os.getpid()}
    os.makedirs(C.game_dir(box.game), exist_ok=True)
    tmp = os.path.join(C.game_dir(box.game), "progress.json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1)
    os.replace(tmp, os.path.join(C.game_dir(box.game), "progress.json"))


NO_ARGS = {"type": "object", "properties": {}}
WAIT_MAX_S = 30                  # one wait call; a longer load is several calls with a check between
TOOLS = {
    "preflight": ("Check that everything is in place before a launch (the pack, the VR files, the meter, the claim).",
                  {"type": "object", "properties": {"headset": {"type": "boolean"}}}),
    "launch_game": ("Launch the game by its pack's launcher (refused unless preflight passed).",
                    {"type": "object", "properties": {"headset": {"type": "boolean"}}}),
    "quit_game": ("Close the game by its own quit (never a kill); puts any swapped save back.", NO_ARGS),
    "game_state": ("Is the game running, did it crash, does its connector answer.", NO_ARGS),
    "spots_find": ("Start the tour: find every spot (save slots, levels) and read the settings' start values.", NO_ARGS),
    "next_step": ("What to do next, in plain words, with the tool to call.", NO_ARGS),
    "spot_reach": ("Get the current spot ready: a save slot swapped in (game closed), or a console jump sent.", NO_ARGS),
    "spot_arrived": ("Say the spot is reached and in play; live-only settings are sent again.",
                     {"type": "object", "properties": {"label": {"type": "string"}}}),
    "settle_wait": ("Wait until the frame times are steady at the spot.", NO_ARGS),
    "look_and_measure": ("Turn the pretend head a full circle and measure every frame meanwhile.", NO_ARGS),
    "setting_set": ("Change one setting to one of its steps, as next_step said.",
                    {"type": "object", "properties": {"knob": {"type": "string"}, "to": {"type": "string"}},
                     "required": ["knob", "to"]}),
    "godmode": ("Switch the game's god mode on at this spot (only when the pack has one; once per spot).", NO_ARGS),
    "report_crash": ("Tell the tour the game crashed on the way to, or at, the spot.", NO_ARGS),
    "report_death": ("Tell the tour the player died at the spot.", NO_ARGS),
    "connector_cost": ("Record the connector's own cost (frame ms with and without it); without numbers: not measured.",
                       {"type": "object", "properties": {"with_ms": {"type": "number"},
                                                         "without_ms": {"type": "number"}}}),
    "apply_all": ("Write every setting to where the game keeps it (the game must be closed).", NO_ARGS),
    "result": ("Write the result for the person (result.txt) and return it.", NO_ARGS),
    "stop": ("Stop the run: quit the game by its own quit, put every save back, write the result.",
             {"type": "object", "properties": {"why": {"type": "string"}}}),
    "wait": ("Pause for a few seconds (at most 30) while the game loads, then say whether it still runs.",
             {"type": "object", "properties": {"seconds": {"type": "number"}}, "required": ["seconds"]}),
    "progress": ("Tell the window what you are doing, in a few plain words.",
                 {"type": "object", "properties": {"doing": {"type": "string"}}}),
}


def call(box, name, args):
    """(result dict, is_error)."""
    if name not in TOOLS:
        return {"say": f"there is no tool '{name}'"}, True
    G.log(box.game, f"tool: {name} {json.dumps(args)}")
    try:
        res, err = getattr(box, name)(**(args or {})), False
    except Refused as e:
        res, err = {"say": str(e), "refused": True}, True
    except SystemExit as e:
        res, err = {"say": str(e)}, True
    except TypeError as e:
        res, err = {"say": f"wrong arguments for {name}: {e}"}, True
    G.log(box.game, f"  -> {'REFUSED ' if err else ''}{res.get('say', '')[:300]}")
    try:
        write_progress(box, last=res.get("say", ""))
    except (OSError, SystemExit):
        pass
    return res, err
