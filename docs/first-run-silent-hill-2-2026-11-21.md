# The first run in a real game: Silent Hill 2, pretend headset, 2026-11-21

The Optimizer 0.1.0, then 0.1.1 (being built) after the fixes below. Run by Claude Code in a Lanes Tester session, with
nobody at the headset.

## The run

- 7 save slots visited, each launched, walked into play, settled, looked around at and measured; one start crash on the
  way (the game's own occasional one), retried by the tour; the result written; the game closed by its own quit after
  every spot; every save put back (checked by hash). 24 minutes; the AI's tokens about 3.46 dollars.
- Verdict at every spot: the processor is the limit (the graphics card 55-60% busy), so no setting was changed.
- **The ranking was noise:** the save swap only replaced the newest slot file, and this game's Continue follows the slot
  last used, so all 7 spots were the same room. 7 measures of one room: 59.7-67.2 frames a second, slowest 1%
  42.9-50.4. That spread is what one spot's noise looks like on this PC.

## What the first run found and fixed (0.1.1)

| Found | Fixed how |
| --- | --- |
| The meter locked its frame file while the game ran: every measure would have failed | `_fsopen` with `_SH_DENYWR`; the reader retries |
| The AI had no way to wait while the game loads | a `wait` tool (30 s at most a call) |
| "Steady" meant no missed frames against the headset's own period: on a 90 Hz pretend headset that never happens below 90 | steady = the frame rate stops moving |
| The pack's `vr_trigger` step: the connector cannot pull a VR trigger | the way into play rewritten: Enter, the menu's Continue, wait for the character, Enter twice |
| The pack's crash sign also appears in starts that do not crash | UEVR's `[Exception Handler]` line |
| The job file forbade the menu call the pack needs | the pack's own `to_play` is the one exception |
| The AI could use every connector tool (memory writes, a kill) | `allow_tools` in the pack: six for Silent Hill 2 |
| The Lanes session holding the game blocked its own run | `OPTIMIZER_RUN_BY_LANES_SESSION` |
| The save swap did not move Continue | the chosen slot over every slot; proved: slot 0 then loaded the town |
| The window counted a spot not yet visited as done | counted as to-do |

## Settled

- "Late" under UEVR's frame warp: one OpenXR frame per game frame, so the meter's interval is the game's own frame time
  (it matched the mod's own frame clock within 0.1 ms). No second clock is needed.

## Still open

- `install.ps1` stops if The Optimizer's window is open (its program file is in use): close the window first, or the
  installer should say so.
- A crash leaves the game's crash reporter window up; nothing in the toolbox closes it (the tour's retry still worked).
- The four live-only settings are not kept by the game at its next start; the result says so, nothing writes them.
- The connector's own cost is not measured.
- The pretend headset draws 1280x1400 an eye and runs its own mirror: whether a spot is processor- or card-limited there
  says little about the real headset. The real test is a run with the headset.
