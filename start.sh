#!/usr/bin/env sh
# Linux/macOS source runner.  The release EXE is Windows-only; this script is
# the supported way to run the same code on other platforms.
set -eu
cd "$(dirname "$0")"
exec python3 main.py "$@"
