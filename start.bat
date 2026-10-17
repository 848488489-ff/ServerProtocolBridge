@echo off
rem ASCII only: cmd reads .bat using the ANSI code page, Chinese here would break parsing.
setlocal
cd /d "%~dp0"
if exist "dist\MCJS-server-protocol-bridge.exe" (
    start "" "dist\MCJS-server-protocol-bridge.exe" %*
) else (
    py -3.14 main.py %*
)
if errorlevel 1 pause