#!/usr/bin/env sh
# Linux/macOS packaging entry point.
#
# PyInstaller cannot cross-compile, so the Windows EXE must be built on
# Windows and this script only ever produces a binary for the platform it
# runs on.  The release channel ships the Windows build; use this on Linux
# or macOS to package the same code for that platform.
#
#   sh tools/build.sh                # build for this platform
#   sh tools/build.sh --smoke        # build and run the packaged checks
set -eu
cd "$(dirname "$0")/.."

if [ -x "$(command -v python3)" ]; then
    PY=python3
else
    PY=python
fi

echo "[build] PyInstaller single file, no UPX/MPRESS ($(uname -s))"
exec "$PY" tools/build.py "$@"
