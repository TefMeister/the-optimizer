# The Optimizer — design

2026-11-21, Build PC, planned with Tefa. Status: **design, Tefa's yes 2026-11-21 (with the live guard removed). Build plan: `plans/2026-11-21-the-optimizer.md`.**
Supersedes `2026-11-21-tune-o-matic-spot-tour-design.md` (that design's tour, ranking and fault fixes are carried over
here; what changed is who drives and where it lives). The tool was called Tune-o-matiC until 2026-11-21.

## 1. Intent

Tefa: *"tune-o-matic i see it being a separate thing altogether that a user starts up, an app, and there chooses the
game that this app then automatically launches and studies for some time without the user doing anything, gathers all
the data and then when done, applies the most optimal settings."* And earlier: *"jump to a game's heaviest spots by
console or save and tune to the worst one"*, *"the graphics never go lower than 72fps"*.

So: an app of its own (not a ride-along helper). You open it, pick a game, press start and walk away. An AI agent
behind it launches the game, visits every spot it can reach, measures, tunes at the worst one, proves the result on
all, closes the game and leaves the best settings in place, with a plain result to read when you come back.

**Description (Tefa: "agreed"):** *"The Optimizer: an app that finds the best-looking settings a PC VR game can hold at
72 frames a second. You pick the game; an AI agent launches it, visits its heaviest spots, measures and tunes, then
leaves the best settings in place. Built and tested with Claude Code; other AI agents that can use MCP tools should
work but are untested."*

## 2. Goals, non-goals, anti-goals

**Goals**
- One window, one game picked, one start button; nothing more asked of the person until the result.
- The AI is not tied to Claude: the toolbox speaks MCP and the job is a plain instruction file. Tuned and tested with
  Claude Code only (Tefa has no other AI to test with).
- Everything measured that can be: the always-on collector rides along, the game's live connector is in.
- Tune at the worst spot the graphics card limits; list processor-limited spots apart ("settings can't fix this").
- Live changes first, restart-only ones last and few. Dangerous spots: god mode when the game has one, else skipped.
- Public repo from the start, version 0.x so people know it is being built (Tefa).

**Non-goals**
- Games with no ready game pack (section 5.3). The app says what is missing; making a pack is a modding session's job.
- Building a game's live connector. A known one is installed; none known = the game goes on a "needs its connector
  built" list.
- Playing levels, fighting, walking routes. A spot is a place reached by save, console or level jump.

**Anti-goals**
- Any of the person's saves left changed (every save-based jump restores and proves by hash).
- An AI let loose on the PC: it may use The Optimizer's tools and the game's connector, nothing else.
- Blurring the picture to fix a processor limit.
- A result that claims a setting is applied when the game will throw it away at the next start.
- A game left running, or killed by force, when the app stops.

## 3. Constraints

- **Windows, the person's own copy of the game, PC VR (OpenXR).** The meter is 64-bit only.
- **The window:** our "apps you open" family look: C#, built with the compiler Windows already has (as Hand Poser and
  Gun Poser are), wide rather than tall, no animations or scan lines (it may hang in the headset through Window View).
- **Clashes:** the app claims the game the way a Tester window does and refuses while a modding session holds it
  (Lanes' lane claim and clash guard, when Lanes is installed; otherwise a lock file of its own).
- **Installs:** helper tools it needs come from our GitHub through Lanes' quiet installer (no Yes clicks); without
  Lanes, the app's own installer step does the same, from official sources only.
- **Privacy:** no login, home path, machine name or e-mail in anything it publishes or commits (it publishes nothing
  by default; the result stays on the PC).
- **SH2 rules** (from Tefa's earlier decisions): DLSS on; view distance never lowered; fog untouched; ray-tracing
  geometry switches out; `r.ScreenPercentage` not a live lever until `[ID SH2-019]` is settled.

## 4. Approaches considered

**Who drives:** A, a plain program with no AI (only games with a pack, stops on any surprise); **B, an AI behind the
window (picked, Tefa: "B, but if possible to suit any AI")**. Any AI is possible because the toolbox is an MCP server
and the job is a plain text file; AIs that run as a program on the PC (Claude Code, Codex, Gemini's command-line tool)
can all use MCP servers. Tested with Claude Code only.

**The window:** **A, C# like Hand Poser (picked by the session; Tefa did not pick another)**: nothing to install, the
same family look, hangs in the headset. B, all Python: one language, plainer window, the odd one out. C, a browser
page: most modern, most moving parts, fiddly in the headset.

**Where it lives:** its own public repo `the-optimizer` (Tefa: "public from the start, but a 0.x version"); Lanes lists
it as an optional extra, like VR Bench. The tuning engine moves there from the Lanes `tune-o-matic` branch.

## 5. The design

### 5.1 The pieces

```
the window (C#)  --starts-->  the AI agent (Claude Code, run in the background with the job file)
     |                              |
     | reads progress.json          | uses only these MCP servers:
     v                              v
 what the person sees        the Optimizer toolbox (Python, MCP)  +  the game's live connector (e.g. UEVR MCP)
                                    |
                                    +-- the tuning engine (today's Tune-o-matiC code + the fault fixes)
                                    +-- the frame meter (our OpenXR layer)
                                    +-- the pretend headset (OpenXR Simulator), menus (Menu-o-matiC),
                                        "is the game OK?" (State-o-matiC), the game pack's reach helpers
```

- **The window:** the game picker (games on this PC that have a pack), the AI picker (Claude Code; "other MCP agents,
  untested"), Start, Stop, Undo; while running, a plain progress list (spot 3 of 7, what it is doing, the last
  numbers); at the end, the result. It never drives the game itself.
- **The AI agent:** started by the window with the job file and a tool list holding only the toolbox and the game's
  connector. For Claude Code: run in the background in a folder of the app's own, with those servers configured and
  every other tool refused. Its words go to a log the window shows.
- **The job file** (`job.md`): the whole job in plain steps, any AI can follow it: preflight, launch, reach, settle,
  look around, measure, rank, tune, final lap, apply, close, result; what to do on each known surprise; when to stop.
- **The toolbox** (an MCP server in Python, standard library only, so nothing to install): one tool per action. The
  rules live in the tools, not in the AI's judgement: a tool refuses what is not allowed (a launch with no VR files,
  a live change of a setting marked unsafe, a second god mode, a save swap while the game runs).

### 5.2 The toolbox's tools

`preflight`, `launch_game`, `quit_game` (the game's own quit; never a kill), `game_state` (State-o-matiC's verdict),
`menu_route` (Menu-o-matiC), `spots_find`, `spot_reach`, `spot_arrived`, `settle_wait`, `look_around` (the pretend
headset turns a full circle in fixed steps), `measure` (the meter + the graphics card's load, with a verdict: holds or
not, card- or processor-limited), `rank`, `tune_next` (the one next change, today's decision code), `setting_set`,
`apply_all`, `connector_cost`, `godmode`, `mark` (a spot marker for the collector), `progress` (what the window shows),
`result`, `undo`. Each returns plain words plus the numbers.

### 5.3 The game pack (one folder per game)

Everything the AI needs to run a game without a person: the settings list (today's profile, with each setting's
lasting home: the file the game reads at start, or "live only"); how to launch (program, start options, environment,
e.g. SH2's Steam id); the menu route to play; how to quit; the spots finder (save slots, levels, travel lines) and
each reach helper; the god mode route or none; the VR files a launch needs; the connector it needs and where to get
it; crash signs (log lines that mean the known start crash); the headset picture size for the pretend headset.
**First pack: Silent Hill 2**, from the reader's table (2026-11-21b note). Lanes sessions write new packs.

### 5.4 The run (what the AI does, in the job file's order)

1. **Preflight:** the pack is complete, VR files beside the launcher, the meter installed, the pretend headset set to
   the pack's picture size, the connector present (installed if a known one is missing), the collector running, the
   game not claimed by a session.
2. **Find the spots** (every save slot, every level the pack lists), skipping those the person struck.
3. **Visit each spot:** reach (save swap and relaunch, console line or level jump) → settle → look around → measure.
   A start crash is retried once, then the spot is unreachable. Danger: god mode when the pack has a route; two deaths
   = unsafe, skipped and listed.
4. **Rank:** the worst card-limited spot is the tuning spot; processor-limited spots go on their own list.
5. **Tune at the tuning spot:** one change per test; live first; restart-only last (each a relaunch and a reach).
6. **The connector's cost:** measured once per game and build (with and without, at the tuning spot); under the noise
   (0.2 ms) nothing is subtracted; otherwise subtracted, and spots near the line are proven without it.
7. **Final lap:** every spot with the final settings; a failing card-limited spot becomes the tuning spot; two rounds
   at most.
8. **Apply:** write every setting to its lasting home. A setting with no lasting home is reported as "holds only while
   you re-apply it", never counted as applied.
9. **Close:** the game's own quit; saves put back and proven; the meter off for that game.
10. **Result** (in the window and a text file): the spots ranked; the settings and what each cost in looks; the
   processor list ("settings can't fix these, short by N ms"); unreachable and unsafe spots; what was measured with.

**Stop rules:** the Stop button; three failed launches in a row; any surprise the job file has no answer for; the
person starting a modding session on that game. Each stop closes the game by its own quit and puts every save back.

### 5.5 Carried over from the spot-tour design

The three fault fixes (start values read live first, then the game's own settings file; a tuning lever that is
safe live, steps from the real start value, no live push from undo while the game runs; refusing a launch with no VR
files); the spots list (robot-found, person can add and strike); the look-around; the ranking; the two-round final lap;
the spot markers for the collector; the connector cost rule. **The live guard is out for now** (Tefa, 2026-11-21:
*"please remove for now, this is a whole another thing to build, something that reliably works in a live game"*): its
code is not carried into the app; it comes back later as a job of its own.

### 5.6 Where the person sees it

```
+--------------------------------------------------------------------------------------------------+
| The Optimizer 0.1.0                                                                               |
| Game: [Silent Hill 2       v]   AI: [Claude Code v]   [ Start ]  [ Stop ]  [ Undo ]              |
|--------------------------------------------------------------------------------------------------|
| Spot 3 of 7   the prison armory       measuring (look-around 8 of 12)                             |
| so far (made-up numbers): slot 0 71 fps, card 95%  |  slot 1 58 fps, processor  |  armory ...      |
| last change: ray-traced reflections off  ->  +1.0 ms                                              |
+--------------------------------------------------------------------------------------------------+
```

## 6. Calls made by the session (Tefa to check)

- The window in C# (Tefa did not pick another).
- The toolbox in Python with no outside libraries, the MCP messages written by hand, so a newcomer installs nothing
  for it beyond Python.
- The AI may use only the toolbox and the game's connector; every rule that protects the PC lives in a tool.
- Unattended runs use the pretend headset; "I'll wear it" in the window runs the final lap in the real headset.
- Repo `the-optimizer`, public, first version 0.1.0; Lanes lists it as an extra.
- The token cost of the AI's run is the person's own account; the README says so plainly.

## 7. Left to the builder

The window's exact layout within the sketch; the toolbox's file split (800-line soft limit); the job file's wording;
the settle detector's numbers and the look-around's step count (named once); tests with a pretend game, a pretend
connector and made-up meter recordings, plus one dry run of the job file by Claude Code against the pretend game.

## 8. Not decided here

- The family renames and front pages: the next job (`claude-memory/plans/2026-11-21-tool-families-and-renames.md`).
- Keeping SH2's live-only values across starts inside our mod: an SH2 board row.
- The live guard (lowering the picture while playing, raising it back): removed for now by Tefa; a job of its own,
  built to work reliably in a live game.
