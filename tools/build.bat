@echo off
rem ASCII only: cmd reads .bat using the ANSI code page, Chinese here would break parsing.
setlocal
cd /d "%~dp0.."
echo [build] PyInstaller + UPX + MPRESS
py -3.14 tools\build.py %*
if errorlevel 1 (
    echo.
    echo Build failed. See output above.
)
pause