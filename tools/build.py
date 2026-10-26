"""Single-file Windows packaging.

    python tools/build.py                 # build, do not execute the artifact
    python tools/build.py --smoke         # build and run the packaged EXE checks
    python tools/build.py --windowed      # no console window (pure GUI)
    python tools/build.py --name MyTool   # custom EXE name

The release EXE is a plain PyInstaller onefile build.  It is deliberately not
touched by UPX or MPRESS: both packers rewrite the PE image, and Windows
antivirus products treat that as a malware signature.  PyInstaller already
compresses its own archive, so a second packer buys almost nothing while
causing false positives.  ``--noupx`` is passed explicitly because UPX being
installed on the build machine is otherwise enough for PyInstaller to use it.
"""

from __future__ import annotations

import argparse
import hashlib
import locale
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / 'dist'
BUILD = ROOT / 'build'

# Default name of the produced EXE: it is the name a user sees and double-clicks.
DEFAULT_NAME = 'Server Protocol Bridge'
# What the smoke test looks for in the --version output (the program name in
# whichever UI language the EXE ends up running with).
SMOKE_NAMES = ('Server Protocol Bridge', '服务器协议转换')

# Modules that are never needed at runtime.  Do not exclude distutils: the
# PyInstaller hook aliases it to setuptools._distutils, and excluding the target
# name breaks the dependency graph.
EXCLUDES = [
    'unittest', 'pydoc', 'idlelib', 'ensurepip', 'sqlite3',
    'tkinter.test', 'turtledemo', 'lib2to3', 'pip', 'setuptools', 'pkg_resources',
    'test', 'numpy', 'PIL', 'PyQt5', 'PySide6',
    # Test tooling and optional back ends that dependency hooks may drag in.
    'pytest', '_pytest', 'pluggy', 'iniconfig', 'py', 'rich', 'pygments', 'chardet',
    # PyCryptodome is only the fallback used when the cryptography wheel is missing.
    'Crypto',
    # The proxy uses websockets.asyncio only.  The legacy/sync/trio back ends are
    # not imported by the application and only add files to unpack.
    'websockets.legacy', 'websockets.sync', 'websockets.trio', 'websockets.__main__',
]


def human(size: int) -> str:
    return '%.2f MB' % (size / 1024 / 1024)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def run_capture(command: list[str], timeout: int = 300, quiet: bool = False) -> subprocess.CompletedProcess:
    """Run an external command and return decoded output.

    Windows consoles default to GBK (cp936).  Capturing as bytes and decoding
    manually keeps a stray undecodable byte from turning a successful build
    into a UnicodeDecodeError.
    """
    if not quiet:
        print('  $ %s' % ' '.join(str(item) for item in command))
    completed = subprocess.run(command, capture_output=True, timeout=timeout)
    encoding = locale.getpreferredencoding(False) or 'utf-8'
    for name in ('stdout', 'stderr'):
        raw = getattr(completed, name) or b''
        setattr(completed, name, raw.decode(encoding, errors='replace'))
    return completed


def smoke_test(exe: Path) -> bool:
    """Run --version once to confirm the EXE starts."""
    try:
        completed = run_capture([str(exe), '--version'], timeout=120)
    except Exception as exc:
        print('    smoke test raised: %s' % exc)
        return False
    output = ((completed.stdout or '') + (completed.stderr or ''))
    ok = completed.returncode == 0 and any(name in output for name in SMOKE_NAMES)
    print('    smoke test: %s' % ('passed' if ok else 'failed'))
    if not ok:
        print('    returncode: %s' % completed.returncode)
        print('    output: %s' % output[:300])
    return ok


def gui_smoke(exe: Path, seconds: float = 6.0) -> bool:
    """Start the GUI hidden and keep it alive for a few seconds."""
    startupinfo = None
    if os.name == 'nt':
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
    try:
        process = subprocess.Popen([str(exe)], startupinfo=startupinfo,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as exc:
        print('    GUI launch raised: %s' % exc)
        return False
    time.sleep(seconds)
    alive = process.poll() is None
    if alive:
        # A PyInstaller onefile bootloader spawns a child that is the actual app,
        # so terminating only this handle leaves that child running as an orphan
        # and holds the EXE locked.  On Windows kill the whole process tree.
        if os.name == 'nt':
            subprocess.run(['taskkill', '/T', '/F', '/PID', str(process.pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           check=False)
        else:
            process.terminate()
        try:
            process.wait(timeout=20)
        except Exception:
            process.kill()
    print('    GUI launch test: %s' % ('passed' if alive else 'failed (process exited early)'))
    return alive


def main() -> int:
    if sys.platform != 'win32':
        print('This build script produces the Windows EXE only.')
        print('On Linux/macOS run the app from source with: sh start.sh')
        return 2
    parser = argparse.ArgumentParser(description='Package Server Protocol Bridge')
    parser.add_argument('--name', default=DEFAULT_NAME, help='EXE name')
    parser.add_argument('--windowed', action='store_true', help='pure GUI build without a console window')
    parser.add_argument('--python', default=sys.executable, help='Python interpreter used for packaging')
    parser.add_argument('--smoke', action='store_true',
                        help='run the packaged EXE (--version / --selftest / GUI) after building')
    args = parser.parse_args()

    # Delete every previous artifact.  config.json and the certificates used to
    # sit in this folder, so they were kept; they now live in the user's
    # configuration folder, so there is nothing to preserve here.
    if DIST.exists():
        for item in DIST.iterdir():
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
            else:
                item.unlink(missing_ok=True)
    if BUILD.exists():
        shutil.rmtree(BUILD, ignore_errors=True)

    command = [
        args.python, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile',
        '--noupx',
        '--name', args.name,
        '--distpath', str(DIST), '--workpath', str(BUILD), '--specpath', str(BUILD),
        '--console' if not args.windowed else '--windowed',
        '--collect-submodules', 'proxy',
        '--collect-submodules', 'websockets.asyncio',
        '--hidden-import', 'websockets.datastructures',
        '--hidden-import', 'websockets.exceptions',
        '--hidden-import', 'websockets.http11',
        '--hidden-import', 'tkinter', '--hidden-import', 'tkinter.filedialog',
        '--hidden-import', 'cryptography',       # required for the encryption handshake
        '--hidden-import', 'mcauth3',            # Microsoft sign-in (optional at runtime)
    ]
    # cryptography's Rust extension links against the ABI3t DLL name even on a
    # standard (GIL) CPython 3.15 build.  CPython ships a forwarding shim in
    # abi3t-compat that maps python3t.dll to python315.dll; without it the
    # frozen EXE silently loses cryptography and cannot do the AES handshake.
    abi3t_dll = Path(sys.base_prefix) / 'abi3t-compat' / 'python3t.dll'
    if abi3t_dll.is_file():
        command += ['--add-binary', '%s%s.' % (abi3t_dll, os.pathsep)]
    icon = ROOT / 'proxy' / 'assets' / 'icon.ico'
    if icon.is_file():
        command += ['--icon', str(icon)]
    version_file = ROOT / 'version_info.txt'
    if version_file.is_file():
        command += ['--version-file', str(version_file)]
    for module in EXCLUDES:
        command += ['--exclude-module', module]
    command.append(str(ROOT / 'main.py'))

    print('[1/3] running PyInstaller (onefile, no UPX/MPRESS)...')
    started = time.time()
    completed = subprocess.run(command, cwd=str(ROOT))
    if completed.returncode != 0:
        print('[failed] PyInstaller returned %d' % completed.returncode)
        return completed.returncode
    exe = DIST / ('%s.exe' % args.name)
    if not exe.exists():
        print('[failed] %s was not produced' % exe)
        return 1
    print('  size: %s, built in %.0f s' % (human(exe.stat().st_size), time.time() - started))

    report = [
        'EXE: %s' % exe,
        'size: %s' % human(exe.stat().st_size),
        'packaging: PyInstaller onefile (no UPX/MPRESS)',
        'SHA256: %s' % sha256(exe),
    ]

    if args.smoke:
        print('[2/3] smoke tests (this executes the packaged EXE)...')
        if not smoke_test(exe):
            print('[failed] the packaged EXE did not start')
            return 1
        selftest = run_capture([str(exe), '--selftest'], timeout=120)
        print('  --- self-test ---')
        print('  ' + (selftest.stdout or '').strip().replace('\n', '\n  '))
        if selftest.returncode != 0:
            print('[failed] self-test did not pass')
            print('  ' + (selftest.stderr or '').strip())
            return 1
        gui_smoke(exe)
    else:
        print('[2/3] smoke tests skipped (pass --smoke to execute the EXE)')

    print('[3/3] summary')
    text = '\n'.join(report)
    (DIST / 'build-report.txt').write_text(text + '\n', encoding='utf-8')
    print(text)
    print('\nartifacts directory: %s' % DIST)
    return 0


if __name__ == '__main__':
    sys.exit(main())
