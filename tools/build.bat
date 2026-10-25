@echo off
rem ASCII only: cmd reads .bat using the ANSI code page.
setlocal
cd /d "%~dp0.."
echo [build] PyInstaller single file, no UPX/MPRESS

where py >nul 2>&1
if %errorlevel%==0 (
    py -3 tools\build.py %*
) else (
    python tools\build.py %*
)
if errorlevel 1 (
    echo.
    echo Build failed. See output above.
)
pause
