#!/usr/bin/env sh
# Build the Linux single-file binary inside WSL2 (Debian/Ubuntu).
#
# PyInstaller cannot cross-compile: this script produces a Linux binary for the
# machine it runs on, not a Windows EXE.  Run it from Windows with
# tools\build_wsl.ps1, or directly inside the WSL distribution:
#
#   sh tools/build_wsl.sh
#
# The first run installs the build dependencies into a private virtual
# environment under ~/.cache (kept out of the source tree) and, when apt is
# available, the GTK/WebKit packages the desktop shell needs.  Later runs reuse
# both.
set -eu
cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-python3}"
VENV="${SPB_LINUX_BUILD_VENV:-$HOME/.cache/server-protocol-bridge/linux-build-venv}"

log() { printf '[wsl] %s\n' "$*"; }

# The GTK backend of pywebview is a system package (python3-gi + WebKitGTK);
# pip cannot provide it reliably.  Install only what is missing, and only when
# this user can use apt without an interactive password.
install_system_packages() {
    [ "${SPB_SKIP_APT:-0}" = "1" ] && return 0
    command -v apt-get >/dev/null 2>&1 || return 0
    # PyInstaller links the frozen app against the Python shared library;
    # Debian/Ubuntu ship python3.11 without it (only python3.11-dev pulls it
    # in), so the package is named after the interpreter's major.minor.
    PYVER="$("$PYTHON" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
    missing=""
    for pkg in python3-venv "libpython$PYVER" python3-gi gir1.2-webkit2-4.1; do
        if ! dpkg -s "$pkg" >/dev/null 2>&1; then
            missing="$missing $pkg"
        fi
    done
    [ -n "$missing" ] || return 0
    if [ "$(id -u)" -eq 0 ]; then
        SUDO=""
    elif sudo -n true 2>/dev/null; then
        SUDO="sudo -n"
    else
        log "missing system packages:$missing"
        log "install them once with: sudo apt-get install$missing"
        return 0
    fi
    log "installing system packages:$missing"
    # ForceIPv4: WSL's resolver often returns only IPv6 for the Debian mirror,
    # and apt then fails even though the network itself is fine.
    if ! $SUDO apt-get -o Acquire::ForceIPv4=true update -qq \
        || ! $SUDO apt-get -o Acquire::ForceIPv4=true install -y -qq $missing; then
        log "warning: system packages could not be installed; continuing."
        log "the binary builds, but its desktop window needs:$missing"
    fi
}

install_system_packages

if [ ! -x "$VENV/bin/python" ]; then
    log "creating build environment: $VENV"
    mkdir -p "$(dirname "$VENV")"
    # --system-site-packages exposes the apt-installed gi/WebKit bindings to
    # the frozen app while pip still owns PyInstaller and the runtime deps.
    "$PYTHON" -m venv --system-site-packages "$VENV"
fi

log "installing build requirements"
"$VENV/bin/python" -m pip install --disable-pip-version-check -q \
    -r requirements-build.txt

log "building (PyInstaller onefile, no UPX/MPRESS)"
exec "$VENV/bin/python" tools/build.py --smoke "$@"
