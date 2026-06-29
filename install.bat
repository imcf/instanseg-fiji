@echo off
:: Install the InstanSeg pixi environment.
:: Run this once from the InstanSeg plugin folder before using the Fiji plugin.

pushd "%~dp0"

where pixi >nul 2>&1
if errorlevel 1 (
    echo ERROR: pixi not found on PATH.
    echo Install it from https://prefix.dev/ and then re-run this script.
    pause
    exit /b 1
)

echo Installing InstanSeg environment (this may take a few minutes)...
pixi install
echo.
echo Done. You can now run the InstanSeg plugin in Fiji.
pause
