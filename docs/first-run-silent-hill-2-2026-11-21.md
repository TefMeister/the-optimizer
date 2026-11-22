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

## The real headset, the same evening (connected, on the table, sensor taped)

- Try 1: the game's occasional start crash, 12 s in (the headset was fine; the ~60 "Failed to initialize Framework" lines
  at a headset start are a normal burst, not a sleeping headset).
- Try 2: the Enter presses also chose CONTINUE on the main menu, so the AI never saw the menu and stopped cleanly. The
  pack now checks for the character too.
- Try 3: reached the town start in the headset (14.3 ms a frame by the mod's clock), but **the meter counted no frame**:
  its live file shows the headset's 72 Hz (so its wait hook ran) and 0 frames, its frame file stayed empty; the tour
  stopped cleanly. Tries 1 and 2 recorded every frame with the same meter. Cause unknown: the next job, with the game
  running and the meter's hooks bisected (other OpenXR layers switched off one at a time by their disable variables).
- Tefa watching the monitor during try 3: the game window showed the "compiling shaders" screen, flickering rapidly,
  while the mod's log said the character was in the town.

## Why the meter counted nothing: another layer (2026-11-21 23:04 to 2026-11-22 00:03, real headset, menu starts)

The meter now counts its calls. In the empty starts it saw **1 wait and 0 frames handed in** for the whole run, while
the game sent ~57 frames a second to the headset: after the first frame the frame calls no longer passed through it.
The other OpenXR layers on this PC were switched off in their registry list (backed up, put back after):

| layers on (besides the meter and Virtual Desktop's) | starts | clean | empty meter | start crash |
| --- | --- | --- | --- | --- |
| all four (OBS mirror, xrFPS, Hand Freeze, Window View) | 13 | 5 | 3 | 5 |
| none | 6 | 6 | 0 | 0 |
| OBS mirror + xrFPS | 3 | 3 | 0 | 0 |
| OBS mirror + xrFPS + Hand Freeze | 3 | 3 | 0 | 0 |
| all four again (stopped by a pause) | 2 | 1 | 0 | 1 |
| Window View alone | 4 | 1 | 1 | 2 |

So the Window View layer is what takes the frame calls past the meter, and very likely what causes Silent Hill 2's
occasional start crash as well `[measured, n small; the crash link is a strong hypothesis]`. Tefa, watching: a crash
may have come when the game window was clicked out of focus (not sure, maybe a coincidence).
Until Window View is fixed: run The Optimizer with Window View's layer off (its registry value set to 1).

## Window View's layer off: the crash stays (2026-11-22 12:20 to 12:37, pretend headset)

11 menu starts with Window View's OpenXR layer off (registry value 1, put back to 0 after), the meter on:
**3 start crashes (starts 4, 5 and 10), 8 clean, no empty meter** `[measured, simulator, n=11]`. Every start that
reached the menu counted all its frames (5100 to 6000; waits = frames). So Window View is not the start crash's cause.
A reading of the crash dumps and of UEVR's own program file puts it in UEVR's Ghosting Fix: for the second eye it
keeps one of the game's scene states and never checks it is still alive, and the game frees it in the start stall
(the SH2 project's note `modding-notes/2026-11-22-start-crash-is-not-window-view.md`).
The empty meter of last night re-read: in those runs UEVR failed to rebuild its eye pictures and handed the headset no
frame at all; the meter counted that correctly, and Window View's code cannot make a layer be skipped.
For The Optimizer this means: a start crash in Silent Hill 2 is the game with UEVR, about 1 start in 4, and the tour's
retry is the right answer to it. The pretend-headset tour over the three spots was not run this time (it was to run
only if the starts were clean).
