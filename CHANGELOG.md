# Changelog

## 0.1.0 (being built), 2026-11-21

- The tuning engine moved over from Lanes' Tune-o-matiC, without the part that changed settings while playing (Tefa:
  "please remove for now").
- Start values are read from the running game first, then the game's own settings file; a setting is changed live
  only when it is marked safe live; undo never sends anything to a running game.
- Game packs, and the first one: Silent Hill 2 (the remake, in UEVR).
- The tour: every spot visited, looked around at and measured; the worst spot the graphics card limits is where it
  tunes; a final lap proves the result on every spot; the settings are written where the game keeps them.
- The toolbox (an MCP server), the job file, and the runner: tested with Claude Code against a pretend game.
- The window.
- Not yet run in a real game.
