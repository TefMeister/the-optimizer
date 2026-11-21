# install.ps1 -- installs The Optimizer for this Windows user: copies the app to %LOCALAPPDATA%\Programs\TheOptimizer,
# fetches the menu helpers (Menu-o-matiC, State-o-matiC) when Lanes is not on this PC, builds the frame meter when it is
# not built yet and Visual Studio Build Tools are here, and puts an icon on the desktop. No administrator rights needed.
#   powershell -ExecutionPolicy Bypass -File install.ps1 [-From <folder with the built app>]
param([string]$From = "")
$ErrorActionPreference = "Stop"
# the helpers come from one fixed Lanes release, so an install never changes under you
$HelpersTag = "v0.121.0"
$HelperFiles = @("menu_o_matic.py", "mom_expect.py", "mom_known.py", "mom_record.py", "mom_route.py", "mom_run.py",
                 "mom_state.py", "mom_steps.py", "mom_window.py", "move_o_matic.py", "state_o_matic.py", "README.md")

if ($From -eq "") { $From = if (Test-Path (Join-Path $PSScriptRoot "dist\TheOptimizer.exe")) { Join-Path $PSScriptRoot "dist" } else { $PSScriptRoot } }
if (-not (Test-Path (Join-Path $From "TheOptimizer.exe"))) { throw "TheOptimizer.exe is not in $From (run build.bat first)" }

# 1. Python 3.12 or newer (The Optimizer needs nothing else installed for it)
$py = (Get-Command python -ErrorAction SilentlyContinue | Where-Object { $_.Source -notmatch "WindowsApps" } | Select-Object -First 1)
if (-not $py) { Write-Output "Python was not found. Install Python 3.12 or newer from python.org (tick 'Add python.exe to PATH'), then run this again."; exit 1 }
$ver = & $py.Source -c "import sys; print('%d.%d' % sys.version_info[:2])"
if ([version]$ver -lt [version]"3.12") { Write-Output "Python $ver is too old: The Optimizer needs 3.12 or newer."; exit 1 }

# 2. the app
$to = Join-Path $env:LOCALAPPDATA "Programs\TheOptimizer"
New-Item -ItemType Directory -Force $to | Out-Null
foreach ($f in "TheOptimizer.exe", "optimizer.ico", "README.md", "LICENSE") {
    if (Test-Path (Join-Path $From $f)) { Copy-Item (Join-Path $From $f) (Join-Path $to $f) -Force }
}
foreach ($d in "engine", "toolbox", "runner", "job", "packs", "meter") {
    if (Test-Path (Join-Path $From $d)) {
        Remove-Item -Recurse -Force (Join-Path $to $d) -ErrorAction SilentlyContinue
        Copy-Item -Recurse (Join-Path $From $d) (Join-Path $to $d)
    }
}

# 3. the menu helpers, when Lanes is not here (Lanes carries its own copy, and The Optimizer uses that one)
$lanes = Get-ChildItem (Join-Path $env:USERPROFILE ".claude\plugins\cache\lanes-plugin\lanes\*\tools\menu-o-matic") -Directory -ErrorAction SilentlyContinue
if ($lanes) {
    Write-Output "The menu helpers: Lanes is here, its own copy is used."
} else {
    $helpers = Join-Path $env:LOCALAPPDATA "TheOptimizer\helpers"
    New-Item -ItemType Directory -Force $helpers | Out-Null
    foreach ($f in $HelperFiles) {
        $url = "https://raw.githubusercontent.com/TefMeister/lanes-plugin/$HelpersTag/plugins/lanes/tools/menu-o-matic/$f"
        Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile (Join-Path $helpers $f)
    }
    Write-Output "The menu helpers fetched from Lanes $HelpersTag into $helpers"
}

# 4. the frame meter: built here when it is not built yet (it needs Visual Studio Build Tools)
$meterDll = Join-Path $to "meter\dist\lanes_tune_meter.dll"
if (-not (Test-Path $meterDll)) {
    $vswhere = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"
    if ((Test-Path $vswhere) -and (Test-Path (Join-Path $to "meter\build.bat"))) {
        & cmd /c "`"$(Join-Path $to 'meter\build.bat')`""
    } else {
        Write-Output "The frame meter is not built: install Visual Studio Build Tools (C++), then run meter\build.bat in $to"
    }
}

# 5. the desktop icon
$shell = New-Object -ComObject WScript.Shell
$lnk = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath("Desktop")) "The Optimizer.lnk"))
$lnk.TargetPath = Join-Path $to "TheOptimizer.exe"
$lnk.WorkingDirectory = $to
$lnk.IconLocation = (Join-Path $to "optimizer.ico") + ",0"
$lnk.Description = "Finds the best-looking settings a PC VR game can hold at 72 frames a second"
$lnk.Save()
Write-Output "Installed to $to, icon on the desktop."
