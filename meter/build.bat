@echo off
rem Builds the Tune-o-matiC frame meter (64-bit OpenXR layer) into dist\, then builds and runs its host test.
rem Needs Visual Studio 2022 Build Tools. `tune.py meter build` runs this; `tune.py meter on <game exe>` installs it.
setlocal
set HERE=%~dp0
set VCVARS=
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
for /f "usebackq delims=" %%i in (`call "%VSWHERE%" -latest -products * -property installationPath`) do set "VCVARS=%%i\VC\Auxiliary\Build\vcvars64.bat"
if not exist "%VCVARS%" (echo Visual Studio Build Tools not found & exit /b 1)
call "%VCVARS%" >nul 2>&1
if not exist "%HERE%dist" mkdir "%HERE%dist"
if not exist "%HERE%build" mkdir "%HERE%build"

cl /nologo /O2 /EHsc /std:c++17 /LD /MT /W4 /I"%HERE%third_party" "%HERE%src\meter_layer.cpp" ^
   /Fo"%HERE%build\\" /Fe"%HERE%dist\lanes_tune_meter.dll" /link /NOLOGO /IMPLIB:"%HERE%build\lanes_tune_meter.lib" >"%HERE%build\layer.build.txt" 2>&1
if errorlevel 1 (type "%HERE%build\layer.build.txt" & echo METER BUILD FAILED & exit /b 1)
findstr /c:"warning" "%HERE%build\layer.build.txt"
copy /y "%HERE%src\lanes_tune_meter.json" "%HERE%dist\" >nul

cl /nologo /O2 /EHsc /std:c++17 /MT /W4 "%HERE%test\meter_test.cpp" /Fo"%HERE%build\\" /Fe"%HERE%build\meter_test.exe" >"%HERE%build\test.build.txt" 2>&1
if errorlevel 1 (type "%HERE%build\test.build.txt" & echo METER TEST BUILD FAILED & exit /b 1)
"%HERE%build\meter_test.exe"
if errorlevel 1 (echo METER TEST FAILED & exit /b 1)
echo METER BUILT: %HERE%dist\lanes_tune_meter.dll
