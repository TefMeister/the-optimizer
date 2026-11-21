// Py.cs -- how the window talks to The Optimizer's Python side: it never drives the game itself. It finds Python, runs
// `python -m engine.cli packs --json` for the game list, starts `runner\run.py` for a run (in the background, no console
// window), and runs `runner\run.py --stop` / `--undo` for the Stop and Undo buttons.
using System;
using System.Diagnostics;
using System.IO;
using System.Text;

static class Py {
    public static string Root;          // the folder holding engine\, toolbox\, runner\, job\, packs\

    public static string FindRoot(string exeDir) {
        foreach (var d in new[] { exeDir, Path.GetDirectoryName(exeDir) ?? exeDir }) {
            if (File.Exists(Path.Combine(d, "runner", "run.py"))) return d;
        }
        return exeDir;
    }

    static string python;
    public static string Python() {
        if (python != null) return python;
        string env = Environment.GetEnvironmentVariable("OPTIMIZER_PYTHON");
        if (!string.IsNullOrEmpty(env) && File.Exists(env)) return python = env;
        foreach (var dir in (Environment.GetEnvironmentVariable("PATH") ?? "").Split(';')) {
            try {
                string p = Path.Combine(dir.Trim(), "python.exe");
                if (dir.Trim().Length > 0 && File.Exists(p) && !p.Contains("WindowsApps")) return python = p;
            } catch (ArgumentException) { }
        }
        return python = "py";
    }

    static ProcessStartInfo Info(string args) {
        var si = new ProcessStartInfo(Python(), args) {
            WorkingDirectory = Root, UseShellExecute = false, CreateNoWindow = true,
            RedirectStandardOutput = true, RedirectStandardError = true,
            StandardOutputEncoding = Encoding.UTF8, StandardErrorEncoding = Encoding.UTF8
        };
        si.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";
        return si;
    }

    // runs to the end and returns what it printed (and the exit code)
    public static string Run(string args, out int code, int timeoutMs) {
        using (var p = Process.Start(Info(args))) {
            var err = p.StandardError.ReadToEndAsync();
            string outText = p.StandardOutput.ReadToEnd();
            if (!p.WaitForExit(timeoutMs)) { code = -1; return outText + "\n(still running after " + timeoutMs / 1000 + " s)"; }
            code = p.ExitCode;
            return code == 0 ? outText : outText + err.Result;
        }
    }

    // a run: started and left going; the window follows it through progress.json
    public static int Start(string args) {
        var si = new ProcessStartInfo(Python(), args) { WorkingDirectory = Root, UseShellExecute = false, CreateNoWindow = true };
        si.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";
        var p = Process.Start(si);
        return p.Id;
    }

    public static string Quote(string s) { return "\"" + s.Replace("\"", "\\\"") + "\""; }

    public static bool Alive(int pid) {
        try { var p = Process.GetProcessById(pid); return !p.HasExited; } catch (Exception) { return false; }
    }
}
