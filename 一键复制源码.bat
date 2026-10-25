@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
    py "%~dp0tools\export_source.py" %*
) else (
    python "%~dp0tools\export_source.py" %*
)

if errorlevel 1 (
    echo.
    echo Export failed. See the message above.
    pause
) else (
    if "%~1"=="" pause
)
endlocal
