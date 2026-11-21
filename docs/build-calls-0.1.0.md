# The Optimizer 0.1.0: the calls made while building it (2026-11-21)

The build followed `docs/plan.md` step by step. Where the plan left a choice open, or turned out wrong, the call
made is below with what it costs if it is wrong. "Deferred" lines are small things left for a later version.

- - T1 Ruling: the meter DLL is moved unchanged; its default output dir is %LOCALAPPDATA%\Lanes\tune\meter, so engine.cli writes `out = <OPTIMIZER meter dir>` into the meter's settings file (the DLL already reads `out =`) — cost if wrong: meter CSVs land in the Lanes folder, found by no reader.
- Task 1: Ruling: ledger moved into the-optimizer's workspace (plan copy docs/plan.md) so the task scripts read this repo's commits — cost if wrong: none
- Task 1: Ruling: the meter 'out =' line and its test were written together with the move, not test-first — a one-line wiring of an existing DLL option — cost if wrong: low, the test now guards it
- Task 1: Ruling: profiles kept in engine/profiles (engine_test checks them; packs reuse the format) — cost if wrong: none
- Task 2: Ruling: connector address is one base (OPTIMIZER_UEVR_BASE, default 127.0.0.1:8899) for both the cvar read and the command — the plan names both routes on one connector — cost if wrong: none
- Task 2: Ruling: `next` sends a change live only while the game runs (S.game_running) and says "restart" whenever it was not sent live — avoids a false "changed in the running game" — cost if wrong: a running game not detected by tasklist gets its change at the next start only
- Task 2: Ruling: unreal-uevr profile: sg.* marked live_safe; r.ScreenPercentage not (restart: true), from the SH2 reader's DLSS-rebuild crashes — cost if wrong: other Unreal games tune sharpness by restart, slower
- Task 2: Ruling: OPTIMIZER_PROFILES_DIR added so tests use a made-up profile — cost if wrong: none
- Task 3: Ruling: `packs [--json]` added to engine.cli here (pre-flight ruling) — cost if wrong: none
- Task 3: Ruling: SH2 launch = the mod's own launcher SH2VR.exe (`play --sim --no-install`, `play --no-install` for the headset), found by globs; vr_files relative to it as the plan says; connector = UEVR-MCP with its MCP server path and a cvar-read health URL [inferred: no source of uevr-mcp's routes on this PC] — cost if wrong: Task 11's first run finds the real launcher folder/health route
- Task 3: Ruling: `to_play` written as steps (wait window, Enter, ContinueGame via connector, wait load, VR trigger) from KNOWN.md — cost if wrong: the first run corrects the route
- Task 3: Ruling: the check also refuses a live_cvar marked `rebuilds` (it could never be changed) — cost if wrong: none
- Task 4: Ruling: look_around ends on the 12th pose (no extra 'face ahead' pose), as the plan's test counts twelve; the next spot's first pose is yaw 0 anyway — cost if wrong: none
- Task 5: Ruling: a vanished robot slot is kept with gone=true (not deleted) so the person's strike/name survive its return — cost if wrong: none
- Task 6: Ruling: the machine also takes T.begin (start a tour), T.settled, T.godmode_on, T.changed, T.cost, T.stop, T.adjusted, T.spot_words — the plan's event list had no way to report a settle, a god mode, a setting change or the connector cost — cost if wrong: none (additions)
- Task 6: Ruling: phases run visiting -> cost -> tuning -> final (cost before tuning so the subtraction applies while tuning); cost phase only when the pack names a connector — cost if wrong: low
- Task 6: Ruling: connector cost is subtracted from the game's own work (work_p95), not from frame intervals (VR intervals are vsync-quantised) — cost if wrong: a spot near the line judged on the raw late frames
- Task 6: Ruling: when no spot fails on the card, the worst holding spot is the tuning spot (to raise the picture); all processor-limited -> straight to applying with no change — cost if wrong: none
- Task 6: Ruling: in tuning a too-short measure is retried once, then the tour stops — cost if wrong: a stop instead of a third try
- Task 6: Ruling: the test's expected change order fixed to rt, shadow, dlss (decide.py lowers least-shows-per-cost first: rt 1/3 before shadow 1/1) — cost if wrong: none, the test was wrong
- Task 7 (pre): Ruling: added NET_DOWN_HOLD_S: a refused connector is not asked again for 5 s (found: tests took 100 s, each refused call costs 2 s on Windows) — test connector_down_remembered RED->GREEN — cost if wrong: a connector that comes up within 5 s of a refusal is read a little later
- Task 7: Ruling: apply/check_applied/result/undo live in engine/finish.py (F.*), not T.* — keeps tour.py under 500 lines; the plan allowed finish.py — cost if wrong: none
- Task 7: Ruling: apply refuses while the game runs (new test apply_refused_while_running): the job closes the game BEFORE apply, not after as the spec's 5.4 order reads — SH2 writes its own settings file as it quits and would undo ours — cost if wrong: none, the order only swaps close and apply
- Task 7: Ruling: apply writes only settings that moved from their start; unchanged ones are listed "(unchanged)" — fewer files touched — cost if wrong: none
- Task 8: Ruling: one toolbox server per game (`server.py --pack <name>`): the tools take no game argument — fewer ways for the AI to go wrong — cost if wrong: none
- Task 8: Ruling: the pretend pack lives in tests/packs/pretend (not packs/), so it never shows in a real person's window; tests and the dry run point OPTIMIZER_PACKS_DIR there — cost if wrong: none
- Task 8: Ruling: spots_find also starts the tour (T.begin); the AI walks the pack's to_play steps with the game's connector tools (the toolbox returns them), the toolbox does the swap and launch — cost if wrong: to_play is AI-driven, checked in Task 11's first run
- Task 8: Ruling: saves are put back after every quit (swap_end), so saves are out of place only while the game runs — cost if wrong: one more swap per relaunch
- Task 8: Ruling: spot_arrived re-sends live-only settings (lost at every start) — found while writing; cost if wrong: none
- Task 8: Ruling: connector_cost takes measured numbers or records "not measured" (a run without the connector has nothing to drive the menus with in 0.1.0) — cost if wrong: the connector's cost is not subtracted (the result says so)
- Task 8: Ruling: preflight does NOT set the pretend headset's picture size (no verified command for it) and says so; the collector check is a note only — cost if wrong: measures at the simulator's own size
- Task 8: Ruling: preflight does not download a missing connector yet; the pack's "get" says where from (an install of a DLL into a game profile is left for a later version) — cost if wrong: the person installs the connector by hand once
- Task 8: Ruling: S.game_running honours OPTIMIZER_RUNNING_FILE (the pretend game's way of "running") — cost if wrong: none (tests only)
- Task 9: Ruling: the agent also gets `--tools ""` (no built-in tool at all: --allowedTools alone only pre-approves, it does not take others away), plus --setting-sources project, --disable-slash-commands, --no-session-persistence; the job goes in on stdin — cost if wrong: none, stricter than the plan
- Task 9: Ruling: run.py also has --show (print the command) and --stop (the window's Stop: ends the agent process, then the toolbox's own stop) — Task 10 needs a stop that works when the AI is stuck — cost if wrong: none
- Task 9: Ruling: job_names_only_real_tools counts only "call `x`" / "then `x`" (the job also writes field names in backticks) — cost if wrong: none
- Task 10: Ruling: Undo goes through `runner/run.py --undo` (F.undo), Stop through `run.py --stop` — one Python entry for the window — cost if wrong: none
- Task 10: Ruling: the window lists only packs whose game is on this PC; an incomplete pack is listed with "(its pack is incomplete)"; a run left going is picked first on opening — cost if wrong: none
- Task 10: Ruling: the GitHub release is marked pre-release, zip of dist\ (app, Python side, Silent Hill 2 pack, built meter, install.ps1); helpers pinned to Lanes v0.121.0 — cost if wrong: none
- Task 10: Ruling: the window test caught a broken line in run.py --undo (a shell-mangled backslash); fixed before the commit; dry run 2 (Claude Code, pretend game) went end to end: visit, tune live + by restart, final lap, apply, done
- Task 11: Ruling: no Lanes version line on the branch (Tune-o-matiC was never in a released version); the merge's version line is written at merge time, its words left in the commit and STATUS.md — cost if wrong: none
- Task 11: Ruling: The Optimizer offered as one of our apps (ours.py "the_optimizer" -> extra ours_the_optimizer), replacing the tune_o_matic extra; clash table, TOOLS.md, EXTRAS.md, CLASHES.md and the smoke test follow — cost if wrong: none
- Final: minor (deferred): the first arrival marks live start values read even when the connector is not up yet (live-only settings then start from the pack's default)
- Final: minor (deferred): the connector's own cost is not measured in 0.1.0 (recorded as "not measured", nothing subtracted)
- Final: minor (deferred): preflight neither sets the pretend headset's picture size nor installs a missing connector (it says so)
