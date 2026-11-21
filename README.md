# The Optimizer

> 🔧 **0.1.0, being built.** Nothing here has been run in a real game yet. Every version stays 0.x until it has
> been. Every file it changes is backed up first, and **Undo** puts them back.

The Optimizer: an app that finds the best-looking settings a PC VR game can hold at 72 frames a second. You pick the
game; an AI agent launches it, visits its heaviest spots, measures and tunes, then leaves the best settings in place.
Built and tested with Claude Code; other AI agents that can use MCP tools should work but are untested.

## What it does

You open the window, pick a game and press **Start**. Then you can walk away. Behind the window an AI agent:

1. checks that everything is in place (the game, its VR files, the frame meter, the pretend headset, the game's
   connector);
2. launches the game and goes through every spot it can reach (save slots, levels), looks around at each and measures;
3. ranks the spots: the worst one the **graphics card** is struggling with is where it tunes. Spots where the
   **processor** is the limit are listed apart, because lowering the picture would not help there;
4. tunes there, one change per test: a setting that shows least for what it costs goes down first, a setting that
   shows most goes up when there is room;
5. proves the result on every spot, writes each setting to where the game keeps it, closes the game with the game's
   own quit, and puts every save back as it was;
6. shows you the result: the spots ranked, the settings and what each costs in looks, and anything it could not fix.

The AI may use **only** The Optimizer's own tools and the game's connector, nothing else on your PC. Every rule that
protects your PC is inside those tools: they refuse what is not allowed.

## What it needs

- **Windows**, your own copy of the game, a **PC VR headset over OpenXR**. The frame meter is 64-bit only.
- **Python 3.12** (nothing else to install for it: The Optimizer uses only what comes with Python).
- **An AI agent that can use MCP tools.** Tested only with [Claude Code](https://claude.com/claude-code). ⚠️ The AI's
  run uses **your own AI account**, and a full tour costs tokens like any long job.
- **A game pack** for the game: one folder in `packs/` saying how to launch it, how to quit it, where its settings
  live and how to reach its spots. The first pack is **Silent Hill 2** (the remake, in UEVR).

## Get it

Download the zip from [Releases](https://github.com/TefMeister/the-optimizer/releases), unzip it, right-click
`install.ps1` and choose **Run with PowerShell**. It checks Python, copies the app to your programs folder, fetches the
two menu helpers it uses (from [Lanes](https://github.com/TefMeister/lanes-plugin), unless Lanes is already on your PC)
and puts a **The Optimizer** icon on the desktop. No administrator rights are needed. Or build it yourself:
`build.bat` (only the C# compiler that ships with Windows), `meter\build.bat` (Visual Studio Build Tools), then
`install.ps1`.

## Use

1. Make sure the game's VR mod and its live connector are installed and work (for Silent Hill 2: the VR mod's own
   launcher and [UEVR-MCP](https://github.com/elliotttate/uevr-mcp)), and that Steam is running.
2. Open **The Optimizer**, pick the game and the AI, press **Start**, and walk away. The middle line says where the run
   is (which spot, what it is doing). The run takes a while: every spot is visited, looked around at and measured, and
   every change is tested.
3. When it is done, the result is in the window (and in `result.txt` in the game's folder under
   `%LOCALAPPDATA%\TheOptimizer`). **Undo** puts every file it changed back as it was. **Stop** at any time closes the
   game by its own quit and puts your saves back.

Tick **I'll wear the headset** to run with the real headset instead of the pretend one.

## How it is built

| Part | What it is |
| --- | --- |
| `app/` | the window (C#) |
| `job/job.md` | the whole job in plain steps, the AI's only instructions |
| `toolbox/` | an MCP server: one tool per step, and every safety rule inside the tools |
| `engine/` | the measuring and tuning (one change per test, the verdicts, the ranking, the tour) |
| `packs/` | one folder per game: how to launch, play, quit and tune it |
| `meter/` | the frame meter: an OpenXR layer that only writes each frame's times down |
| `runner/` | starts the AI with only the toolbox and the game's connector (`agents.json` says how, per AI) |

Tests: `python tests/<name>_test.py` for each part, `tests\app_test.ps1` for the window, and `tests/dry_run.py`, a
whole run by Claude Code against a pretend game (it spends a few tokens).

## Credits

- [OpenXR Simulator](https://github.com/elliotttate/OpenXR-Simulator) by elliotttate, from webhead2oo9's
  [original](https://github.com/webhead2oo9/OpenXR-Simulator): the pretend headset used when nobody wears one.
- [UEVR](https://github.com/praydog/UEVR) by praydog and its contributors, and
  [UEVR-MCP](https://github.com/elliotttate/uevr-mcp) by elliotttate: the connector a UEVR game is tuned through.
- The OpenXR headers in `meter/third_party/openxr` are the Khronos Group's (their licence is beside them).

If you should be credited here and are not, please open an issue.

## Contact

Please open a [GitHub issue](https://github.com/TefMeister/the-optimizer/issues).

## Licence

MIT, see `LICENSE`. A fan-made tool for personal use with games you own; no game files are included.
