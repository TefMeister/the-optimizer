# Changelog

## 0.1.1 (being built), 2026-11-21: fixes from the first look inside Silent Hill 2

- The frame meter no longer locks its own frame file while the game runs: the toolbox measures exactly then, and every
  measure would have failed. The reader also waits a moment and tries again if an older meter holds the file.
- A new `wait` tool (at most 30 s a call): the AI had no way to pause while the game loads.
- "Steady" before measuring now means the frame rate stopped moving, not "no missed frames" (on a 90 Hz pretend headset a
  game at 65 a second misses for good, so every settle ran its full minute).
- A pack can name the only connector tools the AI may use (`allow_tools`); Silent Hill 2's names six.
- The job file says the pack's own way into play (such as a menu's Continue) is the one allowed use of the connector for
  loading.
- The Lanes session that holds a game can start a run on it itself (`OPTIMIZER_RUN_BY_LANES_SESSION`).
- Silent Hill 2's pack: the way into play checked live and rewritten so each step can be done and checked through the
  connector (no VR trigger: the connector cannot pull one, and Enter passes the prompt); the crash sign is UEVR's
  exception-handler line (the old one is also written in starts that do not crash); the console's `god` does nothing in
  this game, so it stays without god mode.

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
