# The Optimizer on Silent Hill 2 with the real headset (2026-11-22 12:52 to 13:29)

Quest 3 by Virtual Desktop, connected and awake, Tefa nearby; Window View's OpenXR layer off for the run (put back
after); `python runner/run.py silent-hill-2 --headset`; the agent was Claude Code (Opus), about 4.30 dollars of tokens.
Logs kept in the SH2 logs folder `2026-11-22-1253-optimizer-headset-tour/` (result, tour, toolbox log, agent log, the
crash and no-frames logs with their dumps).

## What it measured (the frame meter: every frame handed to the headset)

| spot | as found | after the four live changes |
| --- | --- | --- |
| South Vale, the town start | 66.7 a second, slowest 1% 47.3, card 96% (card the limit) | 72.0, slowest 1% 66.1, 0 of 2162 late, card 95% |
| South Vale, the room after the garage | 67.7, slowest 1% 52.8, card 97% (card the limit) | 72.0, slowest 1% 66.5, 0 of 2162 late, card 84% (processor the limit) |
| Toluca Prison, the armory | not reached: two failed starts on the way (one crash, one launch that never started the game) | - |

At the town start, one change at a time: ray-traced reflections off 71.7 / 58.4; shadow size 1024 71.9 / 64.4; corner
shadows off 71.9 / 65.6; local brightness balance off 72.0 / 66.1 `[measured 2026-11-22, real headset, n=1 each]`.
Then the headset picture at 90% (a restart setting): 71.7 / 60.5 and 72.0 / 66.2, the card down to 86%: the processor
is the ceiling, so the smaller picture bought nothing.
Verdict: both spots average a solid 72 with no late frame; the slowest 1% are 1.1-1.2 ms short, set by the processor.

## Faults found (FAULTS.md)

- It KEPT the headset picture at 90% ("costs a lot in looks") though it changed nothing in the slowest frames: a change
  that does not improve the number it was made for should be taken back. Put back by hand with `--undo`.
- The result says "measured with the pretend headset" on a real-headset run.
- The start straight after a crash failed twice (12:57, 13:14): the mod's launcher sat 3 minutes without starting the
  game while the game's crash reporter window was up (closing it at 13:16 did not save that start). 6 minutes lost.
- The tour treated my own quit of a start with no headset pictures as a crash, and after two failed starts it dropped
  the armory for good.
- The four live changes are forgotten at the game's next start (known): nothing makes them stick yet.

## Starts in this run (real headset, Window View's layer off)

9 real starts: 5 clean, 2 start crashes (12:57, 13:14), 2 with no pictures to the headset at all ("D3D12: Failed to
create swapchain" just after the session became ready; 13:00, quit by hand; 13:14, which then also crashed); plus 2
launches that never started the game. So the no-pictures fault happens with Window View off too.
