@echo off
:: build.bat - Build Buddha Mod Loader
:: No Steam SDK required. Uses only Win32 APIs confirmed from import analysis.
::
:: Requirements:
::   Option 1: g++ (MinGW-w64) - https://www.mingw-w64.org/
::   Option 2: MSVC (Visual Studio) - run from "Developer Command Prompt"
::
:: Usage:
::   build.bat          - auto-detect compiler
::   build.bat g++     - force MinGW
::   build.bat msvc     - force MSVC

setlocal enabledelayedexpansion

set "CC="
set "CC_NAME="

:: Detect compiler
if "%~1"=="g++" goto use_gpp
if "%~1"=="msvc" goto use_msvc

:: Auto-detect
where g++ >nul 2>&1
if !errorlevel!==0 (
    set "CC=g++"
    set "CC_NAME=MinGW g++"
    goto compile
)

where cl >nul 2>&1
if !errorlevel!==0 (
    set "CC=cl"
    set "CC_NAME=MSVC cl"
    goto compile
)

echo ERROR: No C++ compiler found.
echo.
echo Install one of:
echo   MinGW-w64: https://www.mingw-w64.org/
echo   Visual Studio: https://visualstudio.microsoft.com/
echo.
echo Or run from Visual Studio Developer Command Prompt for MSVC.
exit /b 1

:use_gpp
set "CC=g++"
set "CC_NAME=MinGW g++"
goto compile

:use_msvc
set "CC=cl"
set "CC_NAME=MSVC cl"
goto compile

:compile
echo.
echo ================================================
echo Buddha Mod Loader Build
echo Compiler: !CC_NAME!
echo ================================================
echo.

set "SRC_DIR=%~dp0"
set "OUT_DIR=%SRC_DIR%bin"
set "DLL_SRC=%SRC_DIR%buddha_mod.cpp"
set "EXE_SRC=%SRC_DIR%load_mod.cpp"

mkdir "!OUT_DIR!" 2>nul

if "!CC!"=="g++" (
    echo [g++] Building buddha_mod.dll...
    g++ -shared -O2 -Wall -Wextra ^
        -o "!OUT_DIR!\buddha_mod.dll" ^
        "!DLL_SRC!" ^
        -nostdlib -lkernel32 -luser32 2>&1
    if errorlevel 1 goto fail

    echo [g++] Building load_mod.exe...
    g++ -O2 -Wall -Wextra ^
        -o "!OUT_DIR!\load_mod.exe" ^
        "!EXE_SRC!" ^
        -lkernel32 -luser32 2>&1
    if errorlevel 1 goto fail

) else (
    echo [MSVC] Building buddha_mod.dll...
    cl /LD /EHsc /O2 /W3 ^
        /Fe"!OUT_DIR!\buddha_mod.dll" ^
        "!DLL_SRC!" ^
        kernel32.lib user32.lib 2>&1
    if errorlevel 1 goto fail

    echo [MSVC] Building load_mod.exe...
    cl /EHsc /O2 /W3 ^
        /Fe"!OUT_DIR!\load_mod.exe" ^
        "!EXE_SRC!" ^
        kernel32.lib user32.lib 2>&1
    if errorlevel 1 goto fail
)

echo.
echo ================================================
echo Build successful!
echo.
echo Output:
echo   DLL: !OUT_DIR!\buddha_mod.dll
echo   EXE: !OUT_DIR!\load_mod.exe
echo.
echo Next steps:
echo   1. Copy both files to your Brutal Legend game directory
echo   2. Start the game
echo   3. Run: load_mod.exe
echo ================================================
exit /b 0

:fail
echo.
echo ================================================
echo BUILD FAILED
echo ================================================
exit /b 1
