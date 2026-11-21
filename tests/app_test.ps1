# app_test.ps1 -- The Optimizer's window: it builds; with --test-dir it lists the pretend game from a test packs folder;
# a run left going (progress.json in phase "visiting") is found when the window opens again, shown, and Stop is on
# (Review Focus 2); Stop is pressed by a posted message only (never the real mouse); and no real file changes (checksums
# before and after). Exit 0 = pass.
#   powershell -ExecutionPolicy Bypass -File tests\app_test.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$fails = 0
function Check($ok, $what) {
    if ($ok) { Write-Output "  ok    $what" } else { Write-Output "FAIL: $what"; $script:fails++ }
}
function Sums($dirs) {
    $out = @{}
    foreach ($d in $dirs) {
        if (Test-Path $d) {
            Get-ChildItem $d -Recurse -File | Where-Object { $_.FullName -notmatch '__pycache__' } |
                ForEach-Object { $out[$_.FullName] = (Get-FileHash $_.FullName -Algorithm SHA256).Hash }
        }
    }
    return $out
}
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class Post {
    [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint m, IntPtr w, IntPtr l);
}
"@

# it builds
& cmd /c "`"$root\build.bat`"" | Out-Null
$exe = Join-Path $root "dist\TheOptimizer.exe"
Check (Test-Path $exe) "the window builds with Windows' own compiler"

# a test folder: the pretend pack, the pretend game's program, a run left going
$t = Join-Path ([IO.Path]::GetTempPath()) ("optimizer-app-" + [Guid]::NewGuid().ToString("N").Substring(0, 8))
New-Item -ItemType Directory -Force "$t\packs", "$t\home", "$t\optimizer\pretend" | Out-Null
Copy-Item -Recurse "$root\tests\packs\pretend" "$t\packs\pretend"
New-Item -ItemType File "$t\home\pretend_game.exe" | Out-Null
'{"game": "pretend", "label": "The pretend game", "phase": "visiting", "round": 0, "at": "slot1", "at_label": "save slot 1 (not named yet)", "step": "look", "spots_total": 3, "spots_done": 1, "doing": "measuring", "last": "", "when": "2026-11-21 20:00:00"}' |
    Set-Content -Encoding UTF8 "$t\optimizer\pretend\progress.json"
$real = @("$root\packs", "$root\job", "$root\engine", "$root\toolbox", "$root\runner", "$env:LOCALAPPDATA\TheOptimizer")
$before = Sums $real

$env:OPTIMIZER_PACKS_DIR = "$t\packs"
$env:OPTIMIZER_PRETEND_HOME = "$t\home"
$env:OPTIMIZER_PRETEND_SAVES = "$t\saves"
$env:OPTIMIZER_RUNNING_FILE = "$t\running"
$env:OPTIMIZER_UEVR_BASE = "http://127.0.0.1:9"
New-Item -ItemType Directory -Force "$t\saves" | Out-Null
$p = Start-Process -FilePath $exe -ArgumentList @("--test-dir", "`"$t`"") -PassThru
$stateFile = "$t\window-state.json"
for ($i = 0; $i -lt 60 -and -not (Test-Path $stateFile); $i++) { Start-Sleep -Milliseconds 250 }
Start-Sleep -Milliseconds 800
$s = Get-Content $stateFile -Raw | ConvertFrom-Json
Check ($s.games -contains "pretend") "the game list holds the pretend game from the test packs folder"
Check ($s.title -eq "The Optimizer 0.1.0") "the title says the version"
Check ($s.selected -eq "pretend" -and $s.stop_enabled -and -not $s.start_enabled) "reopen_finds_running_run: the run left going is shown, Stop is on, Start is off"
Check ($s.progress -match "save slot 1" -and $s.progress -match "2 of 3") "reopen_finds_running_run: it shows where the run is"

# Stop, pressed by a posted message (BM_CLICK), never the real mouse
[Post]::PostMessage([IntPtr][long]$s.stop_hwnd, 0x00F5, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null
for ($i = 0; $i -lt 120; $i++) {
    Start-Sleep -Milliseconds 250
    $s = Get-Content $stateFile -Raw | ConvertFrom-Json
    if ($s.last_action -match "stopped") { break }
}
Check ($s.last_action -match "stopped") "Stop runs the toolbox's own stop (quit by the game's own quit, saves put back)"

[Post]::PostMessage([IntPtr][long]$s.main_hwnd, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null
if (-not $p.WaitForExit(10000)) { Check $false "the window closes on a close message"; }
else { Check $true "the window closes on a close message" }

$after = Sums $real
$same = ($before.Count -eq $after.Count) -and -not ($before.Keys | Where-Object { $before[$_] -ne $after[$_] })
Check $same "no real file changed (checksums before and after)"
Remove-Item -Recurse -Force $t -ErrorAction SilentlyContinue
if ($fails) { Write-Output "app_test: $fails FAILED"; exit 1 } else { Write-Output "app_test: all passed"; exit 0 }
