@echo off
REM Brutal Legend Test Map Loader
REM Copies test map to Win/Mods/ and launches the game

setlocal enabledelayedexpansion

REM Game install path - adjust if your install is different
set "GAME_PATH=<STEAM_PATH>\steamapps\common\BrutalLegend"
set "MOD_PATH=%GAME_PATH%\Win\Mods"

REM Get the directory where this script is located
set "SCRIPT_DIR=%~dp0"
REM Remove trailing backslash
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

echo ================================================
echo Brutal Legend Test Map Loader
echo ================================================
echo.

REM Check if game path exists
if not exist "%GAME_PATH%\BrutalLegend.exe" (
    echo ERROR: Game not found at:
    echo   %GAME_PATH%\BrutalLegend.exe
    echo.
    echo Please update GAME_PATH in this script if your
    echo game is installed in a different location.
    echo.
    pause
    exit /b 1
)

REM Create mod directory if it doesn't exist
if not exist "%MOD_PATH%" (
    echo Creating mod directory: %MOD_PATH%
    mkdir "%MOD_PATH%"
)

REM Find the test map bundle files
set "BUNDLE_NAME=RgS_Testworld"
set "TEST_MAP_DIR=%SCRIPT_DIR%\test_map"

if not exist "%TEST_MAP_DIR%" (
    echo ERROR: Test map not found at:
    echo   %TEST_MAP_DIR%
    echo.
    echo Please run create_test_map.py first:
    echo   python create_test_map.py
    echo.
    pause
    exit /b 1
)

REM Copy the test map bundle files to Win/Mods
echo Copying test map to Win/Mods/...
echo.

set "COPIED=0"
for %%F in ("%TEST_MAP_DIR%\%BUNDLE_NAME%.*") do (
    echo   Copying: %%~nxF
    copy /Y "%%F" "%MOD_PATH%\" >nul
    set /a COPIED+=1
)

if %COPIED% EQU 0 (
    echo ERROR: No bundle files found in %TEST_MAP_DIR%
    echo Expected files: %BUNDLE_NAME%.~h and %BUNDLE_NAME%.~p
    echo.
    echo Please run create_test_map.py first:
    echo   python create_test_map.py
    echo.
    pause
    exit /b 1
)

echo.
echo Successfully copied %COPIED% files to %MOD_PATH%
echo.

REM Ask if user wants to launch the game
set /p LAUNCH="Launch the game now? (Y/N): "
if /i "%LAUNCH%"=="Y" (
    echo.
    echo Launching Brutal Legend...
    start "" "%GAME_PATH%\BrutalLegend.exe"
) else (
    echo.
    echo Skipping game launch.
    echo To play with the test map, manually run:
    echo   "%GAME_PATH%\BrutalLegend.exe"
)

echo.
echo ================================================
echo Test map installed!
echo.
echo To verify installation, check that these files exist:
echo   %MOD_PATH%\%BUNDLE_NAME%.~h
echo   %MOD_PATH%\%BUNDLE_NAME%.~p
echo.
echo Note: The mod loader (buddha_mod.dll) must be installed
echo and active for the test map to load.
echo ================================================

pause
