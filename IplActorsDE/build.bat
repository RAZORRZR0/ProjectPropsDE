@echo off
setlocal enabledelayedexpansion
:: Builds bin\IplActorsDE.asi (x64). Usage: build.bat [nopause]
cd /d "%~dp0"

if not defined DevEnvDir (
    set "VCVARS="
    for %%P in (
        "C:\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
        "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
        "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat"
        "C:\Program Files\Microsoft Visual Studio\2022\Professional\VC\Auxiliary\Build\vcvars64.bat"
        "C:\Program Files\Microsoft Visual Studio\2022\Enterprise\VC\Auxiliary\Build\vcvars64.bat"
    ) do if not defined VCVARS if exist %%P set "VCVARS=%%~P"
    if not defined VCVARS (
        echo [ERROR] Visual Studio x64 build tools not found. Run from an x64 Developer Command Prompt.
        if not "%1"=="nopause" pause
        exit /b 1
    )
    call "!VCVARS!" >nul
)

set "MH=minhook"
if not exist "bin" mkdir "bin"
if not exist "obj" mkdir "obj"
cl.exe /nologo /O2 /W3 /MT /EHsc /std:c++20 /D_CRT_SECURE_NO_WARNINGS /Fo:obj\ ^
    src\main.cpp %MH%\buffer.c %MH%\hook.c %MH%\trampoline.c %MH%\hde\hde64.c ^
    /link /DLL /OUT:bin\IplActorsDE.asi
if errorlevel 1 (
    echo [ERROR] build failed
    if not "%1"=="nopause" pause
    exit /b 1
)
echo Built bin\IplActorsDE.asi
