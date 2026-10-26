"""Program name and version information."""

from __future__ import annotations

from .i18n import tr

# Internal identity of the program: used as the EXE name, the status page,
# the WebSocket Server header and other machine-facing places, so it is always
# English and never translated.
APP_NAME = 'Server Protocol Bridge'
VERSION = '1.1.6'

# Service identifier that shows up in the status page / handshake
SERVICE_NAME = 'server-protocol-bridge'


def app_name() -> str:
    """Display name of the program in the active language."""
    return tr('core.app_name')


def tagline() -> str:
    """One-line description of the program in the active language."""
    return tr('core.tagline')
