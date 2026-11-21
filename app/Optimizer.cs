// Optimizer.cs -- The Optimizer's window: pick a game, pick the AI, Start; then a plain line of where the run is; at the
// end, the result. It never drives the game: Start hands the job to the AI (runner\run.py), Stop and Undo call the
// Python side. Still (no animation, no scan lines: it may hang in the headset through Window View), wide rather than tall.
//
//   TheOptimizer.exe                    the window
//   TheOptimizer.exe --test-dir <dir>   the window, with everything kept in <dir>\optimizer, and its state written to
//                                       <dir>\window-state.json after every refresh (for tests\app_test.ps1)
using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Text;
using System.Threading;
using System.Windows.Forms;

static class Program {
    public const string Version = "0.1.0";
    public static string TestDir;

    [STAThread]
    static int Main(string[] args) {
        for (int i = 0; i < args.Length; i++)
            if (args[i] == "--test-dir" && i + 1 < args.Length) TestDir = args[++i];
        if (TestDir != null) Environment.SetEnvironmentVariable("OPTIMIZER_DIR", Path.Combine(TestDir, "optimizer"));
        Py.Root = Py.FindRoot(AppDomain.CurrentDomain.BaseDirectory.TrimEnd('\\'));
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        Application.Run(new OptimizerUi());
        return 0;
    }

    public static string BaseDir() {
        string env = Environment.GetEnvironmentVariable("OPTIMIZER_DIR");
        if (!string.IsNullOrEmpty(env)) return env;
        return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "TheOptimizer");
    }
}

class OptimizerUi : Form {
    static readonly Color Back = Color.FromArgb(14, 15, 21), Text1 = Color.FromArgb(232, 236, 246),
                          Text2 = Color.FromArgb(150, 160, 190), Accent = Color.FromArgb(56, 196, 232);
    static readonly string[] Active = { "starting", "visiting", "cost", "tuning", "final", "applying" };

    readonly SkinLabel title = new SkinLabel(), where = new SkinLabel(), last = new SkinLabel(), status = new SkinLabel();
    readonly ComboBox games = new ComboBox(), agents = new ComboBox();
    readonly SkinButton start = new SkinButton(), stop = new SkinButton(), undo = new SkinButton();
    readonly SkinCheckBox headset = new SkinCheckBox();
    readonly TextBox result = new TextBox();
    readonly System.Windows.Forms.Timer timer = new System.Windows.Forms.Timer();
    readonly List<string> names = new List<string>();
    string lastAction = "", busy = null;

    public OptimizerUi() {
        Text = "The Optimizer " + Program.Version;
        BackColor = Back; ForeColor = Text1;
        Font = new Font("Segoe UI", 10f);
        ClientSize = new Size(1120, 420);
        MinimumSize = new Size(900, 360);
        string ico = FirstFile(Path.Combine(Py.Root, "optimizer.ico"), Path.Combine(Py.Root, "app", "optimizer.ico"));
        if (ico != null) { Icon = new Icon(ico); Backdrop.Init(this, ico, Back); }

        title.Text = "The Optimizer " + Program.Version;
        title.Font = new Font("Segoe UI Semibold", 17f);
        title.ForeColor = Text1; title.AutoSize = true; title.Location = new Point(18, 12);

        Place(new SkinLabel { Text = "Game", ForeColor = Text2, AutoSize = true }, 20, 66);
        games.DropDownStyle = ComboBoxStyle.DropDownList; games.Bounds = new Rectangle(70, 62, 330, 28);
        Place(new SkinLabel { Text = "AI", ForeColor = Text2, AutoSize = true }, 418, 66);
        agents.DropDownStyle = ComboBoxStyle.DropDownList; agents.Bounds = new Rectangle(444, 62, 250, 28);
        agents.Items.AddRange(new object[] { "Claude Code", "other MCP agents (untested)" });
        agents.SelectedIndex = 0;
        foreach (var c in new[] { games, agents }) { c.BackColor = Color.FromArgb(24, 26, 34); c.ForeColor = Text1; c.FlatStyle = FlatStyle.Flat; }

        Button(start, "Start", 712, Color.FromArgb(40, 120, 90));
        Button(stop, "Stop", 812, Color.FromArgb(140, 52, 52));
        Button(undo, "Undo", 912, Color.FromArgb(52, 58, 80));
        headset.Text = "I'll wear the headset for the final lap"; headset.ForeColor = Text2; headset.AutoSize = true;
        headset.Location = new Point(70, 98);

        where.Font = new Font("Segoe UI Semibold", 12.5f); where.ForeColor = Accent; where.AutoSize = true;
        where.Location = new Point(20, 136);
        last.ForeColor = Text2; last.AutoSize = true; last.Location = new Point(20, 166);
        result.Multiline = true; result.ReadOnly = true; result.ScrollBars = ScrollBars.Vertical;
        result.BackColor = Color.FromArgb(20, 22, 30); result.ForeColor = Text1; result.BorderStyle = BorderStyle.FixedSingle;
        result.Font = new Font("Consolas", 9.5f);
        result.Bounds = new Rectangle(20, 196, 1080, 186);
        result.Anchor = AnchorStyles.Left | AnchorStyles.Right | AnchorStyles.Top | AnchorStyles.Bottom;
        status.ForeColor = Text2; status.AutoSize = true; status.Location = new Point(20, 390);
        status.Anchor = AnchorStyles.Left | AnchorStyles.Bottom;
        Controls.AddRange(new Control[] { title, games, agents, start, stop, undo, headset, where, last, result, status });

        start.Click += (s, e) => StartRun();
        stop.Click += (s, e) => Background("stopping (the game closes by its own quit, the saves go back) ...", "--stop");
        undo.Click += (s, e) => Background("putting every file back ...", "--undo");
        games.SelectedIndexChanged += (s, e) => RefreshNow();
        timer.Interval = 1000;
        timer.Tick += (s, e) => RefreshNow();
        Shown += (s, e) => { LoadGames(); timer.Start(); };
    }

    static string FirstFile(params string[] paths) {
        foreach (var p in paths) if (File.Exists(p)) return p;
        return null;
    }

    void Place(Control c, int x, int y) { c.Location = new Point(x, y); Controls.Add(c); }

    void Button(SkinButton b, string text, int x, Color face) {
        b.Text = text; b.Bounds = new Rectangle(x, 60, 88, 32);
        b.FlatStyle = FlatStyle.Flat; b.BackColor = face; b.ForeColor = Color.White;
        b.FlatAppearance.BorderColor = Color.FromArgb(78, 84, 106);
    }

    string Game() { return games.SelectedIndex >= 0 && games.SelectedIndex < names.Count ? names[games.SelectedIndex] : null; }

    void LoadGames() {
        int code;
        string text = Py.Run("-m engine.cli packs --json", out code, 60000);
        names.Clear(); games.Items.Clear();
        var rows = Json.Arr(code == 0 ? Json.Parse(text.Trim()) : null);
        if (rows == null) { SetStatus("the game list could not be read: " + text.Trim()); RefreshNow(); return; }
        foreach (var r in rows) {
            var o = Json.Obj(r);
            if (o == null || !Json.Bool(o["installed"])) continue;
            names.Add(Json.Str(o["name"]));
            games.Items.Add(Json.Str(o["label"]) + (Json.Bool(o["complete"]) ? "" : "  (its pack is incomplete)"));
        }
        // a run left going (or cut off) is shown first: that is the game the person came back for
        int pick = 0;
        for (int i = 0; i < names.Count; i++) if (IsActive(ReadProgress(names[i]))) { pick = i; break; }
        if (names.Count > 0) games.SelectedIndex = pick;
        else SetStatus("no game here has a pack yet: a game pack says how to launch, quit and tune a game");
        RefreshNow();
    }

    static Dictionary<string, object> ReadProgress(string game) {
        try { return Json.Obj(Json.Parse(File.ReadAllText(Path.Combine(Program.BaseDir(), game, "progress.json")))); }
        catch (Exception) { return null; }
    }

    static bool IsActive(Dictionary<string, object> p) {
        return p != null && Array.IndexOf(Active, Json.Str(Get(p, "phase"))) >= 0;
    }

    static object Get(Dictionary<string, object> d, string k) { object v; return d != null && d.TryGetValue(k, out v) ? v : null; }

    static int AgentPid(string game) {
        try {
            var r = Json.Obj(Json.Parse(File.ReadAllText(Path.Combine(Program.BaseDir(), game, "agent", "run.json"))));
            return (int)Json.Num(Get(r, "pid"), -1);
        } catch (Exception) { return -1; }
    }

    void RefreshNow() {
        string game = Game();
        var p = game == null ? null : ReadProgress(game);
        int pid = game == null ? -1 : AgentPid(game);
        bool agentAlive = pid > 0 && Py.Alive(pid);
        bool active = agentAlive || IsActive(p);
        string line = "", lastLine = "";
        if (p != null) {
            string phase = Json.Str(Get(p, "phase"));
            int total = (int)Json.Num(Get(p, "spots_total"), 0), done = (int)Json.Num(Get(p, "spots_done"), 0);
            string at = Json.Str(Get(p, "at_label")), doing = Json.Str(Get(p, "doing")), step = Json.Str(Get(p, "step"));
            line = PhaseWords(phase, Json.Num(Get(p, "round"), 0));
            if (total > 0 && (phase == "visiting" || phase == "final")) line += "   spot " + Math.Min(done + 1, total) + " of " + total;
            if (at.Length > 0) line += "   " + at;
            if (step.Length > 0 && active) line += "   (" + StepWords(step) + ")";
            if (doing.Length > 0) line += "   " + doing;
            lastLine = Json.Str(Get(p, "last"));
            if (active && !agentAlive) lastLine = "No AI is running this now (it was cut off): Stop closes the game by its own quit and puts everything back.";
        } else if (game != null) line = "ready: press Start and walk away; the AI does the rest";
        if (where.Text != line) where.Text = line;
        if (last.Text != lastLine) last.Text = lastLine.Length > 160 ? lastLine.Substring(0, 160) + " ..." : lastLine;
        string res = game == null ? "" : ReadResult(game);
        if (result.Text != res) result.Text = res;
        bool idle = busy == null;
        Enable(start, idle && game != null && !active);
        Enable(stop, idle && game != null && active);
        Enable(undo, idle && game != null && !active);
        headset.Enabled = !active;
        WriteTestState(line);
    }

    static void Enable(Control c, bool on) { if (c.Enabled != on) c.Enabled = on; }

    static string PhaseWords(string phase, double round) {
        switch (phase) {
            case "starting": return "starting";
            case "visiting": return "visiting the spots";
            case "cost": return "measuring the connector's own cost";
            case "tuning": return "tuning at the worst spot";
            case "final": return "final lap" + (round > 1 ? " (round " + round + ")" : "");
            case "applying": return "writing the settings";
            case "done": return "done";
            case "stopped": return "stopped";
            case "undone": return "everything put back";
            default: return phase;
        }
    }

    static string StepWords(string step) {
        switch (step) {
            case "reach": return "getting there";
            case "settle": return "letting it settle";
            case "god": return "god mode";
            case "look": return "looking around and measuring";
            default: return step;
        }
    }

    static string ReadResult(string game) {
        try { return File.ReadAllText(Path.Combine(Program.BaseDir(), game, "result.txt")).Replace("\r\n", "\n").Replace("\n", "\r\n"); }
        catch (Exception) { return ""; }
    }

    void StartRun() {
        string game = Game();
        if (game == null) return;
        if (agents.SelectedIndex != 0) {
            SetStatus("other AI agents are untested: add its command line to runner\\agents.json (its note says what it needs)");
            return;
        }
        Py.Start("runner\\run.py " + Py.Quote(game) + " --agent claude-code" + (headset.Checked ? " --headset" : ""));
        SetStatus("started: the AI launches the game and tours it; you can walk away");
        RefreshNow();
    }

    void Background(string saying, string flag) {
        string game = Game();
        if (game == null || busy != null) return;
        busy = saying;
        SetStatus(saying);
        RefreshNow();
        var t = new Thread(() => {
            int code;
            string said = Py.Run("runner\\run.py " + Py.Quote(game) + " " + flag, out code, 15 * 60 * 1000).Trim();
            BeginInvoke((Action)(() => {
                busy = null;
                SetStatus(said.Length > 0 ? said.Replace("\r", "").Replace("\n", "; ") : "done");
                RefreshNow();
            }));
        });
        t.IsBackground = true;
        t.Start();
    }

    void SetStatus(string s) {
        lastAction = s;
        string shown = s.Length > 170 ? s.Substring(0, 170) + " ..." : s;
        if (status.Text != shown) status.Text = shown;
        WriteTestState(where.Text);
    }

    void WriteTestState(string progress) {
        if (Program.TestDir == null) return;
        var sb = new StringBuilder("{");
        sb.Append("\"title\":").Append(Json.Write(Text)).Append(",\"games\":[");
        for (int i = 0; i < names.Count; i++) sb.Append(i > 0 ? "," : "").Append(Json.Write(names[i]));
        sb.Append("],\"selected\":").Append(Json.Write(Game() ?? ""));
        sb.Append(",\"start_enabled\":").Append(start.Enabled ? "true" : "false");
        sb.Append(",\"stop_enabled\":").Append(stop.Enabled ? "true" : "false");
        sb.Append(",\"progress\":").Append(Json.Write(progress));
        sb.Append(",\"last_action\":").Append(Json.Write(lastAction));
        sb.Append(",\"stop_hwnd\":").Append(stop.Handle.ToInt64());
        sb.Append(",\"main_hwnd\":").Append(Handle.ToInt64()).Append("}");
        try {
            string path = Path.Combine(Program.TestDir, "window-state.json"), tmp = path + ".tmp";
            File.WriteAllText(tmp, sb.ToString());
            if (File.Exists(path)) File.Delete(path);
            File.Move(tmp, path);
        } catch (IOException) { }
    }
}
