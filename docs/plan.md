# The Optimizer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task
> (Tefa's standing rule: no subagents, work inline). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** a public app, The Optimizer 0.1.0: pick a game, an AI agent (Claude Code tested) launches it, tours every
reachable spot, tunes at the worst card-limited one, proves the result on all, applies the settings, closes the game.

**Architecture:** a new public repo `TefMeister/the-optimizer`. `engine/` = today's Tune-o-matiC code (moved from the
Lanes `tune-o-matic` branch, without the live guard) plus the fault fixes, the game packs, the spots and the tour.
`toolbox/` = an MCP server (stdio, JSON-RPC written by hand) whose tools are thin calls into the engine and enforce
every rule. `job/job.md` = the whole job in plain steps for any AI. `app/` = the C# window, which starts the AI in the
background and shows `progress.json`. `meter/` = the frame meter (moved as is).

**Tech Stack:** Python 3.12 standard library only; C# built with Windows' own `csc.exe` (as Hand Poser); Claude Code
run with `-p`, `--mcp-config`, `--strict-mcp-config`, `--allowedTools`, `--output-format stream-json` (all present in
this PC's `claude --help`, 2026-11-21); the OpenXR Simulator's command files (`head_pose_command.json`: x, y, z metres,
yaw/pitch/roll radians); Menu-o-matiC and State-o-matiC from the lanes-plugin repo (`tools/menu-o-matic/`).

**Spec:** `plugins/lanes/docs/specs/2026-11-21-the-optimizer-design.md` (Tefa's yes 2026-11-21, live guard removed).
Detail carried from `specs/2026-11-21-tune-o-matic-spot-tour-design.md` and the SH2 reader note
`silent-hill-2-remake-vr/modding-notes/2026-11-21b-reader-tune-o-matic-live-safety.md`.

## Global Constraints

- Repo `the-optimizer`, **public** (Tefa: "Public from the start, but a 0.x version"), MIT licence as our other apps
  ("Copyright (c) 2026 Tefa (TefMeister)"), first version **0.1.0**, every version 0.x until Tefa says otherwise.
- The description, verbatim: *"The Optimizer: an app that finds the best-looking settings a PC VR game can hold at 72
  frames a second. You pick the game; an AI agent launches it, visits its heaviest spots, measures and tunes, then
  leaves the best settings in place. Built and tested with Claude Code; other AI agents that can use MCP tools should
  work but are untested."*
- **No live guard** anywhere in the repo (Tefa: "please remove for now").
- Never force-kill a game; quit by the pack's own quit route. Every save-based jump restores every save, proven by hash.
- The AI is given only the toolbox and the game's connector; the toolbox refuses whatever is not allowed.
- No home paths, logins, machine names, e-mail in any file (Lanes' privacy guard runs on commits on this PC).
- Numbers named once in `engine/settings.py` with a one-line why; files 800 lines soft, 1,500 hard.
- Messages in plain English; the window still (no animation), wide rather than tall.
- SH2: DLSS on; view distance never lowered; fog untouched; `r.ScreenPercentage` never changed live; the six values
  our plugin's `tuning.cpp` holds never listed.
- Tests use made-up recordings, a pretend game, a pretend connector, a temp folder (`OPTIMIZER_DIR`); nothing real.

## Review Focus

1. **The AI asks for something the job file never mentions** (a file write, a shell command): it is not in its tool
   list, so the run goes on; the toolbox log shows no such call. → Task 9 test `runner_allows_only_two_servers`.
2. **The window closed while a run is going**: the AI and the game keep a consistent state; reopening shows the run
   and offers Stop (which quits the game and restores saves). → Task 10 test `reopen_finds_running_run`.
3. **The game's settings file rewritten by the game between our write and its start** (SH2 does this): `apply` reads
   it back after the next start and reports any setting the game undid as "did not stick". → Task 7 test
   `apply_reports_undone_setting`.
4. **A pack whose save folder holds more or fewer slots than last time**: `spots_find` adds the new ones, keeps the
   person's strikes, and never measures a slot that vanished. → Task 5 test `find_after_slots_change`.
5. **A stop in the middle of a save swap** (Stop pressed, or a crash): the next start of the toolbox finds the swap
   in force and restores before anything else. → Task 8 test `stop_mid_swap_restores_first`.

---

### Task 1: the repo, the engine moved over, the guard left behind

**Files:**
- Create repo `TefMeister/the-optimizer` (`gh repo create TefMeister/the-optimizer --public --description "<the
  description>"`), cloned to `~/github-backups/the-optimizer`.
- Create: `engine/settings.py` (from `tune_common.py`: the numbers and folders; base folder
  `%LOCALAPPDATA%\TheOptimizer`, `OPTIMIZER_DIR` in tests), `engine/knobs.py`, `engine/read.py`, `engine/decide.py`
  (from `tune_knobs.py`, `tune_read.py`, `tune_decide.py`), `engine/cli.py` (from `tune.py` without `cmd_guard` and the
  `GUARD_*` numbers), `meter/` (copied whole), `README.md`, `LICENSE`, `CHANGELOG.md` (0.1.0, "being built"),
  `docs/design.md` and `docs/plan.md` (copies of the spec and this plan).
- Test: `tests/engine_test.py` (from `tools/tests/tune_test.py`, the guard checks removed).

**Interfaces:**
- Produces: `engine` as a package imported by later tasks (`from engine import settings as S, knobs as K, read as R,
  decide as D`); `python -m engine.cli <command>` keeps `readers | profiles | meter ... | start | measure | next | set
  | status | undo`.

- [ ] **Step 1:** create the repo and copy the files; rename imports; delete every guard line.
- [ ] **Step 2: run** `python tests/engine_test.py`. Expected: all `ok`, exit 0; `grep -ri guard engine` empty.
- [ ] **Step 3:** README: the description, "0.1.0, being built", what it needs (Windows, Python 3.12, PC VR over
  OpenXR, an AI agent; tested only with Claude Code), that the AI's run uses the person's own AI account, credits
  (OpenXR Simulator: elliotttate and webhead2oo9; UEVR and UEVR-MCP authors; the "open an issue if you should be
  credited" line; contact = a GitHub issue).
- [ ] **Step 4: commit and push** `The Optimizer 0.1.0 (being built): the tuning engine moved over from Tune-o-matiC, without the live guard`.

### Task 2: start values from the truth, safe live changes, undo that never pushes live (faults 1 and 2)

**Files:** Modify `engine/knobs.py`, `engine/cli.py`, `engine/settings.py`; Test `tests/fixes_test.py` (a pretend
connector answering `GET /api/console/cvar?name=X` with `{"float": v}` and `POST /api/console/command`).

**Interfaces:**
- Produces: `K.live_value(knob) -> str | None`; `K.start_value(knob, game) -> tuple[str | None, str]` (source
  `"live" | "file" | "default" | "unknown"`); knob kinds `"gsa_option"` (the pair `("<key>", <n>)` inside an ini's
  `GFXSettings=(GsaOptions=(...))`) and `"live_cvar"` (no file); knob flags `"game_owned"` (file route never read),
  `"live_safe"` (may be changed live), `"rebuilds"` (never changed live); `S.game_running(exe) -> bool` (tasklist;
  `OPTIMIZER_FAKE_RUNNING=1|0` in tests).

- [ ] **Step 1: write the failing tests:** `start_reads_live_first` (connector says 58.0 → start step `"58"` of
  `["50","54","58","62","66.7"]`, message says "(read live)"); `start_falls_back_when_connector_down` (no connector,
  `gsa_option` `Adv_DLSSQuality` in `GFXSettings=(GsaOptions=(("Quality", -1),("Adv_DLSSQuality", 2)))`, steps
  `["1","2","3"]` → index 1, "(from the game's settings file)", no exception); `game_owned_never_reads_user_script`
  (a `user_script.txt` line `r.ScreenPercentage 100` ignored → "unknown"); `gsa_option_write_keeps_the_rest` (only the
  pair changes, the rest byte for byte, a backup first); `live_change_refused_unless_live_safe` (a knob without
  `live_safe`, or with `rebuilds`, is never sent live); `undo_no_live_push_while_running`
  (`OPTIMIZER_FAKE_RUNNING=1`: files restored, nothing sent, "restart the game" said).
- [ ] **Step 2: run** `python tests/fixes_test.py`. Expected: six FAIL.
- [ ] **Step 3: implement.** `start_value` order: live (knob has `live` and the connector answers) → file (unless
  `game_owned`) → `default` → unknown. A `gsa_option` knob may carry `"map"` (step → display name).
- [ ] **Step 4: run** `fixes_test.py` and `engine_test.py`. Expected: exit 0.
- [ ] **Step 5: commit** `Start values read live first, then the game's own settings file; live changes only where safe; undo never pushes live while the game runs`.

### Task 3: the game pack format, its checker, and the Silent Hill 2 pack

**Files:** Create `engine/pack.py`, `packs/silent-hill-2/pack.json`; Test `tests/pack_test.py`.

**Interfaces:**
- Produces: `P.load(name) -> dict`, `P.check(pack) -> list[str]` (problems in plain words; empty = complete),
  `P.list_packs() -> list[str]`, `P.installed(pack) -> bool` (the game's program exists on this PC).
  Pack fields: `name`, `label`, `exe` (program name), `find_exe` (Steam app id and/or folder patterns), `launch`
  (`{"program": <launcher relative to the game or a pack tool>, "args": [...], "env": {...}}`), `vr_files` (paths
  relative to the launcher's folder), `to_play` (a Menu-o-matiC route name, or connector calls listed in order),
  `quit` (the game's own quit: a connector console line or a route), `settings` (the knob list, as a profile),
  `spots_find` (`save_glob` + `slot_re` + `reach`, and/or `levels` + `reach`), `swap_tool` (the save swapper the pack
  ships), `godmode` (`null` or `{"console": "<line>"}`), `connector` (`{"name": "UEVR-MCP", "check_url": ..., "get":
  <where from>}`), `crash_signs` (log file + lines that mean a known start crash), `picture` (`{"w": 2688, "h": 2880}`
  per eye for the pretend headset), `settle` (seconds steady, default 5).
- SH2 pack values: `exe` `SHProto-Win64-Shipping.exe`; `env` `SteamAppId=2124490`, `SteamGameId=2124490`; `vr_files`
  `["uevr\\UEVRBackend.dll", "uevr\\openxr_loader.dll"]`; `to_play`: the main menu's `ContinueGame(Movie=null,
  NonSkippableLen=0)` through the connector, then a VR trigger past "press any button"; `quit` the console `quit`;
  `crash_signs` `Scene state passed to FSceneView constructor is null` in `%APPDATA%\UnrealVRMod\SHProto-Win64-Shipping\
  log.txt`; `picture` 2688 × 2880; `godmode` null (first run tries the console `god`, Task 11); settings: from the
  spot-tour plan's SH2 list (`rt_reflections`, `shadow_res`, `ao`, `local_exposure` as `live_cvar` + `live_safe`;
  `dlss_level` `gsa_option` restart-only `game_owned`; `xr_scale` ini restart-only), each with its lasting home
  (`"keep": "<file>"` or `"keep": null` = live only) and the left-out list as `notes`; `swap_tool` a copy of SH2's
  `saveswap.py` (ours, from the game repo) inside the pack.

- [ ] **Step 1: write the failing tests** `sh2_pack_complete` (`check` empty), `pack_missing_quit_is_named`
  (a pack without `quit` → one problem "no way to quit the game by its own means"), `no_live_knob_without_safe`.
- [ ] **Step 2: run.** Expected: FAIL.
- [ ] **Step 3: implement** `pack.py`; write the SH2 pack; copy `saveswap.py` in with its header unchanged.
- [ ] **Step 4: run** `pack_test.py`. Expected: exit 0.
- [ ] **Step 5: commit** `Game packs: the format, a checker, and the first pack (Silent Hill 2)`.

### Task 4: measuring at a spot: the look-around and the shared measuring window

**Files:** Create `engine/look.py`; Modify `engine/read.py` (`measure_window` from `cli.py`'s `_measure_rows`),
`engine/settings.py` (`LOOK_STEPS = 12`, `LOOK_STEP_S = 2.5`, `LOOK_HEIGHT_M = 1.7`, `SIM_DATA_DIR` =
`%LOCALAPPDATA%\OpenXR-Simulator`, `OPTIMIZER_SIM_DATA` in tests); Test `tests/tour_test.py`.

**Interfaces:**
- Produces: `R.measure_window(exe, seconds, flat=False, csv=None) -> (rows, gpu, why)`;
  `L.head(x, y, z, yaw_deg, pitch_deg=0) -> bool` (writes `head_pose_command.json` atomically: write a temp file,
  replace, retried); `L.look_around(headset=False) -> float` (seconds taken).

- [ ] **Step 1: write the failing tests** `look_writes_twelve_heads` (yaws 0, 30 ... 330 in radians, `LOOK_STEP_S`
  patched to 0) and `measure_window_unchanged` (`engine_test.py` still passes).
- [ ] **Step 2: run.** Expected: FAIL.
- [ ] **Step 3: implement.**
- [ ] **Step 4: run** both. Expected: exit 0.
- [ ] **Step 5: commit** `A fixed look-around on the spot, and one measuring window for everything`.

### Task 5: the spots list

**Files:** Create `engine/spots.py`; Test `tests/tour_test.py`.

**Interfaces:**
- Produces: `<OPTIMIZER_DIR>/<game>/spots.json`, a list of `{"id", "label", "by": "robot"|"person", "struck",
  "reach": {"kind": "save_slot"|"console"|"level_jump"|"route", "value"}}`; `SP.find(game, pack) -> int` (added),
  `SP.load(game)`, `SP.active(game)`, `SP.add(game, label, kind, value)`, `SP.strike(game, id)`,
  `SP.name(game, id, label)`.

- [ ] **Step 1: write the failing tests** `find_lists_every_slot` (7 fake `.sav` → `slot0`..`slot6`, labels "save
  slot N (not named yet)"), `find_twice_adds_none`, `person_add_and_strike`, `find_after_slots_change` (Review Focus 4).
- [ ] **Step 2: run.** Expected: FAIL.
- [ ] **Step 3: implement.**
- [ ] **Step 4: run.** Expected: exit 0.
- [ ] **Step 5: commit** `The spots list: found by the robot, added or struck by the person`.

### Task 6: the tour's step machine (visit, rank, tune, final lap)

**Files:** Create `engine/tour.py`; Modify `engine/settings.py` (`SPOT_CRASH_RETRIES = 1`, `SPOT_DEATHS_UNSAFE = 2`,
`FINAL_LAP_ROUNDS = 2`, `CONNECTOR_NOISE_MS = 0.2`); Test `tests/tour_test.py`.

**Interfaces:**
- Consumes: Tasks 2-5; `D.verdict`, `D.choose`.
- Produces: `<game>/tour.json` = `{"phase": "visiting"|"cost"|"tuning"|"final"|"applying"|"done"|"stopped", "round",
  "at", "step": "reach"|"settle"|"look", "spots": {id: {"status": "todo"|"done"|"unreachable"|"unsafe", "summary",
  "verdict", "crashes", "deaths"}}, "tuning_spot", "processor": [ids], "connector_ms", "changes": [...]}`;
  `T.next_step(game) -> dict` (`{"do": <action name>, "say": <plain words>, ...args}`), `T.arrived(game, label=None)`,
  `T.measured(game, rows, gpu)`, `T.crashed(game)`, `T.died(game)`, `T.rank(tour) -> (tuning_spot, processor_ids)`,
  `T.marker(game, event)` (writes `<meter dir>/<stamp>_<stem>.frametime-spots.tsv`: `t_unix, spot, event, settings`).

- [ ] **Step 1: write the failing tests:** `rank_picks_worst_card_bound`; `all_processor_bound_changes_nothing`
  (phase goes to `applying` with no change, every spot named "settings can't fix this"); `short_measure_is_not_ranked`;
  `crash_retry_then_unreachable`; `died_twice_is_unsafe` (with a pack `godmode`, `next_step` asks for it before the
  look); `final_lap_two_rounds_max`; `tour_resumes_mid_spot`; `strike_mid_tour`; `cost_below_noise_subtracts_nothing`;
  `cost_above_noise_is_subtracted`; `restart_only_settings_come_last`; `markers_written_per_look`.
- [ ] **Step 2: run.** Expected: FAIL.
- [ ] **Step 3: implement** the machine as the spec's 5.4 steps 2-7; ranking by `low1_fps` ascending among failing
  card-limited spots.
- [ ] **Step 4: run** `tour_test.py`, `engine_test.py`. Expected: exit 0.
- [ ] **Step 5: commit** `The tour: visit every spot, rank, tune at the worst card-limited one, prove on all`.

### Task 7: apply, the result, undo

**Files:** Modify `engine/tour.py` (or `engine/finish.py` if `tour.py` passes 600 lines); Test `tests/tour_test.py`.

**Interfaces:**
- Produces: `T.apply(game) -> list[str]` (each setting written to its `keep` home, backed up first; `keep: null` →
  "holds only while re-applied"); `T.check_applied(game) -> list[str]` (after the next start: any setting the game
  undid → "did not stick"); `T.result(game) -> list[str]` (also `<game>/result.txt`); `T.undo(game)`.

- [ ] **Step 1: write the failing tests** `apply_reports_live_only`, `apply_reports_undone_setting` (Review Focus 3),
  `result_lists_everything` (ranked spots, settings with their look cost, the processor list with "short by N ms",
  unreachable / unsafe spots, what was measured with), `undo_restores_every_file`.
- [ ] **Step 2: run.** Expected: FAIL.
- [ ] **Step 3: implement.**
- [ ] **Step 4: run.** Expected: exit 0.
- [ ] **Step 5: commit** `Apply the settings to where the game keeps them, say what did not stick, the result, undo`.

### Task 8: the toolbox (the MCP server)

**Files:** Create `toolbox/server.py` (stdio JSON-RPC: `initialize`, `tools/list`, `tools/call`), `toolbox/tools.py`
(the tool table), `toolbox/game.py` (launch, quit, state, menus, save swaps, the connector); Test
`tests/toolbox_test.py` (drives `server.py` over pipes with a pretend game program and a pretend connector).

**Interfaces:**
- Consumes: everything in `engine/`; `menu_o_matic.py run <route>` and `state_o_matic.py watch <window>` from the
  helpers folder (`S.HELPERS_DIR`: the lanes-plugin `tools/menu-o-matic/` folder, found or fetched in Task 10).
- Produces: MCP server name `optimizer`; tools (each returns `{"say": <plain words>, ...numbers}`):
  `preflight`, `launch_game`, `quit_game`, `game_state`, `spots_find`, `next_step`, `spot_reach`, `spot_arrived`,
  `settle_wait`, `look_and_measure`, `setting_set`, `godmode`, `report_crash`, `report_death`, `apply_all`, `result`,
  `stop` (quit + restore saves), `progress` (written to `<game>/progress.json` for the window).
  `preflight` covers the spec's 5.4 step 1: the pack complete, VR files, the meter, the pretend headset at the pack's
  `picture` size, the collector running (when Lanes is installed), and the connector: missing and the pack names where
  to get it → installed through Lanes' `quiet_install.py` when present, else downloaded from that official source;
  no known connector → "this game needs its connector built first" and the run does not start.
  Rules enforced here: `launch_game` refuses when `preflight` fails or the game is claimed by a session (Lanes' lane
  claim file when present, else `<OPTIMIZER_DIR>/claim.json`); `spot_reach` of a save slot refuses while the game runs;
  `godmode` only once per spot and only with the pack's route; `quit_game` never kills; at server start a save swap in
  force is restored before anything else.

- [ ] **Step 1: write the failing tests** `lists_every_tool`, `launch_refused_without_vr_files`,
  `launch_refused_when_claimed`, `swap_refused_while_running`, `stop_mid_swap_restores_first` (Review Focus 5),
  `quit_never_kills` (the pretend game's quit route is used; no `taskkill` call recorded).
- [ ] **Step 2: run** `python tests/toolbox_test.py`. Expected: FAIL.
- [ ] **Step 3: implement.**
- [ ] **Step 4: run** every test file. Expected: exit 0.
- [ ] **Step 5: commit** `The toolbox: every step of the job as an MCP tool, with the safety rules inside the tools`.

### Task 9: the job file and the runner (Claude Code in the background)

**Files:** Create `job/job.md`, `runner/run.py`, `runner/agents.json`; Test `tests/runner_test.py`.

**Interfaces:**
- Produces: `job.md`: the spec's 5.4 order as numbered steps, each naming the toolbox tool to call, what to do on
  each `say` it can return, and the stop rules (Stop pressed, three failed launches in a row, any surprise not listed:
  call `stop`, then `result`). `runner/agents.json`: `{"claude-code": {"cmd": ["claude", "-p", "<job>",
  "--mcp-config", "<file>", "--strict-mcp-config", "--allowedTools", "mcp__optimizer__*", "mcp__<connector>__*",
  "--output-format", "stream-json", "--verbose"], "tested": true}}` plus an `"other"` entry with `"tested": false`
  and a note on what an agent needs (MCP servers, a non-interactive mode, a tool allow-list).
  `python runner/run.py <pack> --agent claude-code [--headset]` writes the MCP config (the toolbox + the pack's
  connector), starts the agent in `<OPTIMIZER_DIR>/<game>/agent/`, keeps its stream in `agent.log`, returns its exit.
- [ ] **Step 1: write the failing tests** `runner_allows_only_two_servers` (Review Focus 1: the built command holds
  `--strict-mcp-config` and exactly the two allow patterns), `runner_writes_mcp_config`, `job_names_only_real_tools`
  (every tool named in `job.md` exists in `tools.py`).
- [ ] **Step 2: run.** Expected: FAIL.
- [ ] **Step 3: implement**; check the flags against this PC's `claude --help` once more before the commit.
- [ ] **Step 4: run** the tests, then **one dry run**: `run.py` against the pretend game pack (`packs/pretend/`, a
  pretend game program from the toolbox tests) with Claude Code. Expected: `result.txt` written, the pretend game
  quit by its route, `agent.log` holds no tool outside the two servers.
- [ ] **Step 5: commit** `The job file and the runner: Claude Code runs the job with only the toolbox and the connector`.

### Task 10: the window (C#)

**Files:** Create `app/Optimizer.cs` (+ split files under 800 lines), `app/optimizer.ico` (an original icon, themed),
`build.bat` (Windows' `csc.exe`, as Hand Poser's), `install.ps1` (Python check; fetches the lanes-plugin
`tools/menu-o-matic/` folder at a pinned release tag into `%LOCALAPPDATA%\TheOptimizer\helpers` when Lanes is not
installed; the meter build; a Desktop shortcut); Test `tests/app_test.ps1` (builds; starts the window with
`--test-dir`; clicks by PostMessage only; checks files before and after by checksum).

**Interfaces:**
- Consumes: `P.list_packs`/`P.installed` (through `python -m engine.cli packs --json`), `runner/run.py`,
  `<game>/progress.json`, `<game>/result.txt`, the toolbox's `stop` and the engine's `undo` (through `engine.cli`).
- Produces: one wide window as the spec's 5.6 sketch: game list (packs whose game is on this PC), AI list (Claude
  Code; "other MCP agents (untested)"), Start, Stop, Undo, "I'll wear the headset for the final lap"; the progress
  lines; the result. Title `The Optimizer 0.1.0`. No animation.

- [ ] **Step 1: write the failing test** `app_test.ps1`: builds; the game list holds `pretend` from a test packs dir;
  `reopen_finds_running_run` (Review Focus 2: a `progress.json` with phase `visiting` → the window shows it and Stop is
  enabled); no real file changed.
- [ ] **Step 2: run.** Expected: FAIL.
- [ ] **Step 3: implement.**
- [ ] **Step 4: run** `app_test.ps1` and every Python test. Expected: all pass.
- [ ] **Step 5: commit and push**; tag `v0.1.0`; a GitHub release "0.1.0 (being built)" with the built window and the
  meter, the README's caution at the top.

### Task 11: Lanes and the notes

**Files (Lanes, branch `tune-o-matic`):** Modify `plugins/lanes/begone/collector.py` (`tune_meter_files`: the
Optimizer's meter folder too, glob `*_{stem}.frametime*`), `plugins/lanes/docs/EXTRAS.md` (The Optimizer as an extra,
with its read-more link), remove `tools/tune-o-matic/` (moved; a line in the Lanes CHANGELOG says where it went);
Test `plugins/lanes/tools/tests/collector_test.py` (`optimizer_meter_and_markers_collected`).
**Notes:** `claude-memory/FAULTS.md` (the three Tune-o-matiC rows: "fixed in The Optimizer, not checked in a game",
still OPEN), `STATUS.md`, the SH2 board: a `[FLAT]` row "The Optimizer's first run on Silent Hill 2 (simulator)", which
also tries the console `god` and records the answer in the SH2 pack and KNOWN.md, and settles what "late" means under
UEVR's frame warp against `stat unit` before any verdict counts; `TefMeister/INDEX.json` and the front page row;
`thanks.py` for anyone credited who is not starred yet; the activity log line.

- [ ] **Step 1: write the failing collector test.** **Step 2: run**, FAIL. **Step 3: implement.** **Step 4: run**
  the Lanes tests touched. Expected: exit 0.
- [ ] **Step 5: commit** (Lanes branch; it merges with the branch after the one-PC test) and push the notes.

## Not in this plan (said out loud)

- The live guard: removed by Tefa for now; a job of its own, built to work reliably in a live game.
- The first real run on Silent Hill 2: a Tester-window job after Task 11 (its board row is written in Task 11).
- The tool families and renames: the next job (`claude-memory/plans/2026-11-21-tool-families-and-renames.md`).
- Testing with an AI other than Claude Code: on the Workshop PC, when one is available there.
