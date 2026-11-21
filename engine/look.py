"""look.py - the look-around on a spot: the pretend headset (OpenXR Simulator) turns the head a full circle in fixed
steps, so the measuring window sees every direction, not only the one the game happened to face.

The simulator reads head_pose_command.json from its folder: x, y, z in metres, yaw, pitch, roll in radians (the same
file VR Bench writes). Each pose is written to a temp file first and then put in place in one step, so the simulator
never reads half a file. With the person wearing the real headset nothing is written: the same time passes and the
person is asked to look around.
"""
import json
import math
import os
import time

from engine import settings as C

HEAD_CMD = "head_pose_command.json"


def head(x, y, z, yaw_deg, pitch_deg=0):
    """Point the pretend head. True when the pose was written."""
    d = C.sim_data_dir()
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, HEAD_CMD)
    tmp = path + ".optimizer-tmp"
    body = json.dumps({"x": x, "y": y, "z": z, "yaw": math.radians(yaw_deg), "pitch": math.radians(pitch_deg),
                       "roll": 0.0})
    for _ in range(C.HEAD_WRITE_TRIES):
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(body)
            os.replace(tmp, path)
            return True
        except OSError:
            time.sleep(0.05)
    try:
        os.remove(tmp)
    except OSError:
        pass
    return False


def look_around(headset=False):
    """Turn a full circle in C.LOOK_STEPS steps, C.LOOK_STEP_S each. Returns the seconds it took."""
    t0 = time.time()
    for i in range(C.LOOK_STEPS):
        if not headset:
            head(0.0, C.LOOK_HEIGHT_M, 0.0, i * 360.0 / C.LOOK_STEPS)
        time.sleep(C.LOOK_STEP_S)
    return time.time() - t0
