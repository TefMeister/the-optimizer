"""read.py - The Optimizer's readers: the numbers one test run is judged on, from whichever programs this PC has.

  frame meter   (ours, any OpenXR game)  every VR frame: how long it took, how long the game waited, late or not
  nvidia-smi    (with NVIDIA's driver)   how busy the graphics card was, its temperature and clock, once a second
  PresentMon    (Intel, optional)        a FLAT game's frame times and the card's time per frame; it needs
                                         administrator rights or the "Performance Log Users" group to read
Each reader that is missing is said once in the result, never guessed around.
"""
import csv
import glob
import json
import os
import shutil
import statistics
import subprocess
import tempfile
import threading
import time

from engine import settings as C

LATE_FACTOR = 1.5      # a frame that took over 1.5 target frames was late (the headset showed an old one)
PCT = 100


# ---- the frame meter -------------------------------------------------------------------------------------------
def meter_csvs(exe_stem=None):
    pat = f"*_{exe_stem}.frametime.csv" if exe_stem else "*.frametime.csv"
    return sorted(glob.glob(os.path.join(C.meter_dir(), pat)), key=os.path.getmtime)


def read_meter_csv(path):
    rows = []
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = [ln for ln in f if not ln.startswith("#")]
    for r in csv.DictReader(lines):
        try:
            rows.append({k: float(v) for k, v in r.items() if k})
        except (TypeError, ValueError):
            continue          # a half-written last line while the game still runs
    return rows


def last_seconds(rows, seconds):
    if not rows or not seconds:
        return rows
    end = rows[-1]["t_ms"]
    return [r for r in rows if r["t_ms"] >= end - seconds * 1000]


def summarize(rows, target_fps):
    """The frames of one test, in the numbers the verdict uses. None when there are too few to judge."""
    frames = [r for r in rows if r.get("interval_ms", 0) > 0]
    if not frames:
        return None
    iv = sorted(r["interval_ms"] for r in frames)
    periods = [r["period_ms"] for r in frames if r.get("period_ms", 0) > 0]
    hz = 1000.0 / statistics.median(periods) if periods else None
    target = min(target_fps, hz) if hz and hz < target_fps - 0.5 else target_fps
    late_ms = LATE_FACTOR * 1000.0 / target
    late = sum(1 for v in iv if v > late_ms)
    p99 = iv[min(len(iv) - 1, int(len(iv) * 0.99))]
    work = sorted(r.get("work_ms", 0) for r in frames)
    secs = sum(iv) / 1000.0
    return {
        "frames": len(frames), "seconds": round(secs, 1),
        "fps": round(len(frames) / secs, 1) if secs else 0,
        "low1_fps": round(1000.0 / p99, 1) if p99 else 0,
        "late_pct": round(late * PCT / len(frames), 2),
        "late": late,
        "worst_ms": round(iv[-1], 1),
        "hz": round(hz, 1) if hz else None,
        "target": round(target, 1),
        "work_p95_ms": round(work[min(len(work) - 1, int(len(work) * 0.95))], 2),
        "frame_ms": round(1000.0 / target, 2),
    }


def read_live(exe_stem):
    path = os.path.join(C.meter_dir(), f"{exe_stem}.live.json")
    try:
        with open(path, encoding="utf-8") as f:
            v = json.load(f)
        v["_age_s"] = time.time() - os.path.getmtime(path)
        return v
    except (OSError, ValueError):
        return None


# ---- nvidia-smi ------------------------------------------------------------------------------------------------
def nvsmi():
    return shutil.which("nvidia-smi") or (r"C:\Windows\System32\nvidia-smi.exe"
                                          if os.path.isfile(r"C:\Windows\System32\nvidia-smi.exe") else None)


GPU_FIELDS = ["load", "temp_c", "mhz", "mem_mb", "watts"]


def gpu_once():
    exe = nvsmi()
    if not exe or os.environ.get("OPTIMIZER_NO_GPU"):
        return None
    try:
        out = subprocess.run([exe, "--query-gpu=utilization.gpu,temperature.gpu,clocks.gr,memory.used,power.draw",
                              "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=10).stdout
        vals = [v.strip() for v in out.splitlines()[0].split(",")]
        return {k: float(v) for k, v in zip(GPU_FIELDS, vals) if v.replace(".", "", 1).isdigit()}
    except (OSError, IndexError, subprocess.SubprocessError):
        return None


class GpuSampler:
    """Samples the card once a second on a side thread while a test runs."""
    def __init__(self):
        self.samples, self._stop = [], threading.Event()
        self._t = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        while not self._stop.is_set():
            s = gpu_once()
            if s is None:
                return
            self.samples.append(s)
            self._stop.wait(C.NVSMI_EVERY_S)

    def start(self):
        self._t.start()
        return self

    def stop(self):
        self._stop.set()
        self._t.join(timeout=15)
        return gpu_summary(self.samples)


def gpu_summary(samples):
    if not samples:
        return None
    loads = [s["load"] for s in samples if "load" in s]
    temps = [s["temp_c"] for s in samples if "temp_c" in s]
    return {"samples": len(samples),
            "load_avg": round(statistics.mean(loads), 1) if loads else None,
            "load_max": max(loads) if loads else None,
            "temp_max": max(temps) if temps else None}


# ---- PresentMon (flat games) -----------------------------------------------------------------------------------
def presentmon():
    p = C.conf("presentmon")
    if p and os.path.isfile(p):
        return p
    for name in ("PresentMon.exe", "presentmon.exe", "PresentMon"):
        w = shutil.which(name)
        if w:
            return w
    for g in (r"C:\Program Files\Intel\PresentMon\PresentMon*\PresentMon*.exe",
              os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Intel.PresentMon.Console*\*.exe")):
        hits = glob.glob(g)
        if hits:
            return hits[0]
    return None


def presentmon_rows(exe_name, seconds):
    """[{'interval_ms', 'gpu_ms'}] for one flat game, or (None, why)."""
    pm = presentmon()
    if not pm:
        return None, "PresentMon is not on this PC (python -m engine.cli readers says how to get it)"
    out = os.path.join(tempfile.mkdtemp(prefix="optimizer-pm-"), "pm.csv")
    try:
        r = subprocess.run([pm, "--process_name", exe_name, "--output_file", out, "--timed", str(int(seconds)),
                            "--terminate_after_timed", "--stop_existing_session"],
                           capture_output=True, text=True, timeout=seconds + 60)
    except (OSError, subprocess.SubprocessError) as e:
        return None, f"PresentMon did not run: {e}"
    if not os.path.isfile(out):
        said = (r.stderr or r.stdout or "").strip().splitlines()[-1:] or ["no words"]
        return None, f"PresentMon wrote nothing (it needs administrator rights or the Performance Log Users group): {said[0]}"
    rows = []
    with open(out, encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f):
            iv = r.get("MsBetweenPresents") or r.get("FrameTime") or r.get("MsBetweenDisplayChange")
            gpu = r.get("MsGPUActive") or r.get("GPUBusy") or r.get("MsGPUBusy")
            try:
                rows.append({"interval_ms": float(iv), "gpu_ms": float(gpu) if gpu else 0.0, "period_ms": 0.0})
            except (TypeError, ValueError):
                continue
    t = 0.0
    for r in rows:
        t += r["interval_ms"]
        r["t_ms"] = t
    return rows, None


# ---- what is on this PC ----------------------------------------------------------------------------------------
def readers():
    """Every reader with whether it is here and how to get it. The ones marked 'ours' ship in Lanes."""
    layer = os.path.join(C.layer_dir(), "lanes_tune_meter.dll")
    built = os.path.join(C.METER_SRC, "dist", "lanes_tune_meter.dll")
    return [
        {"name": "frame meter (ours)", "here": os.path.isfile(layer),
         "what": "every VR frame of any OpenXR game: late frames, the headset's rate, the game's own work per frame",
         "get": "python -m engine.cli meter on <game program>" + ("" if os.path.isfile(built) else " (after: python -m engine.cli meter build)")},
        {"name": "nvidia-smi", "here": bool(nvsmi()),
         "what": "how busy the graphics card is and how hot: tells a card limit from a processor limit",
         "get": "comes with NVIDIA's graphics driver"},
        {"name": "PresentMon (Intel)", "here": bool(presentmon()),
         "what": "frame times of a FLAT game (the meter covers VR); needs administrator rights to read",
         "get": "python quiet_install.py run winget:Intel.PresentMon.Console"},
        {"name": "OpenXR Simulator", "here": os.path.isdir(C.conf("openxr_sim_dir") or
                                                           r"D:\claude video game stuff\tools\OpenXR-Simulator"),
         "what": "a pretend headset: a tuning test with nobody in the headset (its frame rate is not the headset's)",
         "get": "an extra in Lanes (openxr-sim.py)"},
        {"name": "BeG0nE camera jitter", "here": True,
         "what": "after a headset test, says whether the picture stepped: a smooth frame rate can still judder",
         "get": "ships in Lanes: begone.py new after each headset test"},
        {"name": "xrFPS (elliotttate)", "here": None,
         "what": "the frame rate as a graph inside the headset, for the person wearing it",
         "get": "outside.py get xrfps"},
    ]
