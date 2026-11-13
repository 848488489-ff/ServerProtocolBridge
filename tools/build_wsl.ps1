# Builds the Linux single-file binary inside WSL2.
#
# PyInstaller cannot cross-compile, so this does not produce a Windows EXE; it
# uses the WSL distribution's own Python and GTK libraries to build the Linux
# build of the same release.  The first run installs the build dependencies in
# a private virtual environment under the WSL home directory.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File tools\build_wsl.ps1
#   powershell -ExecutionPolicy Bypass -File tools\build_wsl.ps1 -Distro Ubuntu-26.04
#
# The result is dist/Server Protocol Bridge (an ELF executable).
param(
    [string]$Distro = 'Debian'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

# wsl.exe strips backslashes from arguments passed through interop, so the
# Windows path is sent with forward slashes and resolved to /mnt/... by
# wslpath *inside* the distribution.  Capturing wslpath output in PowerShell
# would mangle the UTF-8 Chinese directory names on the way back.
$winPath = $root -replace '\\', '/'

Write-Host "[wsl] building Linux binary in $Distro"
& wsl.exe -d $Distro -- bash -lc 'cd "$(wslpath -a "$1")" && sh tools/build_wsl.sh' _ "$winPath"
exit $LASTEXITCODE
