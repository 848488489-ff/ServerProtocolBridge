#!/usr/bin/env python3
"""Server Protocol Bridge -- program entry point.

Running it (or double-clicking the EXE) opens the GUI; add --no-gui to run in
command line mode.

    python main.py
    python main.py --no-gui --target mc244.com --port 8443
    python main.py --check
"""

from __future__ import annotations

import sys

CLI_FLAGS = ('--no-gui', '--cli', '--check', '--selftest', '--install-cert', '--version',
             '--check-update', '--update-url', '--no-update-check', '--help', '-h')


def _use_cli(argv) -> bool:
    for item in argv:
        if item in CLI_FLAGS:
            return True
        if item.startswith('--target') or item.startswith('--config'):
            return True
    return False


def main() -> int:
    argv = sys.argv[1:]
    if _use_cli(argv):
        from mcjs_proxy.cli import main as cli_main

        return cli_main(argv)
    try:
        from mcjs_proxy.gui import main as gui_main
    except ImportError as exc:  # no tkinter -> fall back to the command line
        from mcjs_proxy.config import Config
        from mcjs_proxy.i18n import set_language, tr

        # Mirror what the CLI would do, so the notice below already honours the
        # language stored in config.json.
        set_language(Config.load().language)
        print(tr('core.main.gui_fallback', error=exc))
        print(tr('core.main.gui_fallback_hint'))
        from mcjs_proxy.cli import main as cli_main

        return cli_main(argv)
    return gui_main()


if __name__ == '__main__':
    sys.exit(main())
