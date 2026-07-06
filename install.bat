@echo off
:: Install the InstanSeg pixi environment into %APPDATA%\InstanSeg so that
:: Fiji's script discovery never sees the environment files.

set "INSTALL_DIR=%APPDATA%\InstanSeg"

echo InstanSeg environment will be installed to:
echo   %INSTALL_DIR%
echo.

where pixi >nul 2>&1
if errorlevel 1 (
    echo ERROR: pixi not found on PATH.
    echo Install it from https://prefix.dev/ and then re-run this script.
    pause
    exit /b 1
)

if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

if not exist "%~dp0pixi.toml" (
    echo ERROR: pixi.toml not found next to this script.
    echo Expected: %~dp0pixi.toml
    pause
    exit /b 1
)

echo Copying environment files...
copy /Y "%~dp0pixi.toml" "%INSTALL_DIR%\pixi.toml"
if exist "%~dp0pixi.lock" copy /Y "%~dp0pixi.lock" "%INSTALL_DIR%\pixi.lock"

if not exist "%INSTALL_DIR%\pixi.toml" (
    echo ERROR: failed to copy pixi.toml to %INSTALL_DIR%.
    pause
    exit /b 1
)

pushd "%INSTALL_DIR%"
echo Installing InstanSeg environment (this may take a few minutes)...
pixi install
popd

echo.
echo Done. Python environment is at:
echo   %INSTALL_DIR%\.pixi\envs\default
echo You can now run the InstanSeg plugin in Fiji.
pause
