@echo off
rem Builds The Optimizer's window into dist\ with the C# compiler that ships with Windows (.NET Framework 4), and puts
rem the Python side beside it (engine, toolbox, runner, job, packs) so dist\ is the whole app. Then install.ps1 for the
rem desktop icon. The frame meter has its own build (meter\build.bat, Visual Studio Build Tools).
setlocal
set HERE=%~dp0
if not exist "%HERE%dist" mkdir "%HERE%dist"
"%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe" /nologo /target:winexe /optimize+ /win32icon:"%HERE%app\optimizer.ico" ^
   /out:"%HERE%dist\TheOptimizer.exe" "%HERE%app\*.cs"
if errorlevel 1 (echo APP BUILD FAILED & exit /b 1)
copy /y "%HERE%app\optimizer.ico" "%HERE%dist\" >nul
for %%d in (engine toolbox runner job packs) do (
   robocopy "%HERE%%%d" "%HERE%dist\%%d" /MIR /XD __pycache__ /NFL /NDL /NJH /NJS /NP >nul
)
if exist "%HERE%meter\dist\lanes_tune_meter.dll" (
   if not exist "%HERE%dist\meter\dist" mkdir "%HERE%dist\meter\dist"
   copy /y "%HERE%meter\dist\lanes_tune_meter.*" "%HERE%dist\meter\dist\" >nul
)
copy /y "%HERE%README.md" "%HERE%dist\" >nul
copy /y "%HERE%LICENSE" "%HERE%dist\" >nul
copy /y "%HERE%install.ps1" "%HERE%dist\" >nul
echo BUILD OK: %HERE%dist
