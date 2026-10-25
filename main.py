#!/usr/bin/env python3
"""Server Protocol Bridge -- program entry point.

Running it (or double-clicking the EXE) opens the CustomTkinter window; add
--no-gui to run in command line mode.

    python main.py
    python main.py --no-gui --target play.example.net --port 8443
    python main.py --check
    python main.py --web-ui                  # Web UI only
    python main.py --web-ui --gui            # window and Web UI
    python main.py --web-ui --web-port 9000  # pick the browser port
"""

from __future__ import annotations

import sys

# Options that select the command line interface.  The Web UI switches are
# deliberately not in this tuple: they choose an interface, they do not want
# the CLI parser.
CLI_FLAGS = ('--no-gui', '--cli', '--check', '--selftest', '--install-cert',
             '--version', '--check-update', '--update-url', '--no-update-check',
             '--help', '-h')


def _use_cli(argv) -> bool:
    for item in argv:
        if item in CLI_FLAGS:
            return True
        if item.startswith('--target') or item.startswith('--config'):
            return True
    return False


def _option(argv, name: str, default: str) -> str:
    """Return ``--name value`` or ``--name=value`` from the command line."""
    for index, item in enumerate(argv):
        if item == name and index + 1 < len(argv):
            return argv[index + 1]
        if item.startswith(name + '='):
            return item.split('=', 1)[1]
    return default


def main() -> int:
    argv = sys.argv[1:]

    if _use_cli(argv):
        from proxy.cli import main as cli_main
        return cli_main(argv)

    web_requested = '--web-ui' in argv
    gui_requested = '--no-gui' not in argv and ('--gui' in argv or not web_requested)

    if web_requested:
        from proxy.webserver import start_web_ui

        try:
            from proxy.config import Config

            defaults = Config.load()
            default_host, default_port = defaults.web_host, str(defaults.web_port)
        except Exception:
            default_host, default_port = '127.0.0.1', '8765'
        host = _option(argv, '--web-host', default_host)
        try:
            port = int(_option(argv, '--web-port', default_port))
        except ValueError:
            port = int(default_port) if default_port.isdigit() else 8765
        url, error = start_web_ui(host, port)
        if url:
            print('Web UI: %s' % url)
        else:
            print('Web UI could not start: %s' % error, file=sys.stderr)

    if gui_requested:
        try:
            from proxy.gui_ctk import main as gui_main
        except ImportError as exc:  # no tkinter / no CustomTkinter
            from proxy.config import Config
            from proxy.i18n import set_language, tr

            set_language(Config.load().language)
            print(tr('core.main.gui_fallback', error=exc))
            print(tr('core.main.gui_fallback_hint'))
            from proxy.cli import main as cli_main
            return cli_main(argv)
        return gui_main()

    if web_requested:
        import time
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print('\nShutting down...')
            return 0

    return 0


if __name__ == '__main__':
    sys.exit(main())
