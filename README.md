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
