"""Step-by-step commit script: one commit per module, so the history is easy to trace.

    py -3.14 tools\\commit_steps.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

STEPS = [
    ('feat: implement RFC6455 WebSocket framing and handshake', ['mcjs_proxy/wsproto.py']),
    ('feat: implement SRV lookup and target server reachability probe', ['mcjs_proxy/resolver.py']),
    ('feat: implement config load/save, address parsing and validation', ['mcjs_proxy/config.py']),
    ('feat: implement the WebSocket-to-TCP forwarding core', ['mcjs_proxy/proxy.py']),
    ('feat: implement the tkinter GUI', ['mcjs_proxy/gui.py']),
    ('feat: implement CLI mode and the program entry point', ['mcjs_proxy/cli.py', 'main.py']),
    ('test: add self-tests (certificate handshake / frame codec / end-to-end relay)', ['tests/test_all.py']),
    ('build: add PyInstaller + UPX + MPRESS packaging scripts', ['tools/build.py', 'tools/build.bat', 'start.bat']),
    ('docs: write README, config example and dependency notes', ['README.md', 'config.example.json', 'requirements.txt']),
]


def git(*args: str) -> int:
    return subprocess.run(['git', *args], cwd=str(ROOT)).returncode


def main() -> int:
    for message, files in STEPS:
        existing = [item for item in files if (ROOT / item).exists()]
        if not existing:
            print('[skip] files do not exist: %s' % ', '.join(files))
            continue
        if git('add', '--', *existing) != 0:
            print('[failed] git add: %s' % ', '.join(existing))
            return 1
        staged = subprocess.run(['git', 'diff', '--cached', '--quiet'], cwd=str(ROOT)).returncode
        if staged == 0:
            print('[skip] no changes: %s' % message)
            continue
        if git('commit', '-q', '-m', message) != 0:
            print('[failed] git commit: %s' % message)
            return 1
        print('[commit] %s' % message)

    print('\n--- commit history ---')
    subprocess.run(['git', 'log', '--oneline'], cwd=str(ROOT))
    print('--- untracked / unstaged ---')
    subprocess.run(['git', 'status', '--short'], cwd=str(ROOT))
    return 0


if __name__ == '__main__':
    sys.exit(main())
