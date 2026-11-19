"""Single-file packaging (Windows EXE, Linux/macOS binary).

    python tools/build.py                 # build, do not execute the artifact
    python tools/build.py --smoke         # build and run the packaged checks
    python tools/build.py --windowed      # GUI-subsystem build (no console; default keeps a console)
    python tools/build.py --name MyTool   # custom binary name

PyInstaller cannot cross-compile: the binary is always for the platform that
runs this script.  Windows uses tools/build.bat, Linux/macOS tools/build.sh,
and WSL2 users can run tools/build_wsl.ps1 (or tools/build_wsl.sh inside the
distribution) for the Linux binary.

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
# What the smoke test looks for in the --version output (the program name,
# which is always English now that the project is English-only).
SMOKE_NAMES = ('Server Protocol Bridge',)

# Modules that are never needed at runtime.  Do not exclude distutils: the
# PyInstaller hook aliases it to setuptools._distutils, and excluding the target
# name breaks the dependency graph.
EXCLUDES = [
    'unittest', 'pydoc', 'idlelib', 'ensurepip', 'sqlite3',
    'tkinter.test', 'turtledemo', 'lib2to3', 'pip', 'setuptools', 'pkg_resources',
    'test', 'numpy', 'PIL', 'PyQt5', 'PySide6',
    # The desktop shell no longer uses tkinter/CustomTkinter; drop them so the
    # frozen binary does not carry tcl/tk and the CustomTkinter package.
    'tkinter', 'customtkinter',
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
    """Run --version once to confirm the EXE starts and the CLI still prints.

    The release build is console-subsystem (default), so --version output is
    printed to the inherited console directly.  Empty output is tolerated only
    for headless environments where no console can be attached.
    """
    try:
        completed = run_capture([str(exe), '--version'], timeout=120)
    except Exception as exc:
        print('    smoke test raised: %s' % exc)
        return False
    output = ((completed.stdout or '') + (completed.stderr or ''))
    ok = completed.returncode == 0 and (
        not output or any(name in output for name in SMOKE_NAMES))
    print('    smoke test: %s' % ('passed' if ok else 'failed'))
    if not ok:
        print('    returncode: %s' % completed.returncode)
        print('    output: %s' % output[:300])
    return ok


def gui_smoke(exe: Path, seconds: float = 6.0) -> bool:
    """Start the GUI hidden and keep it alive for a few seconds."""
    if not IS_WINDOWS:
        # A Linux build host may still have a display (WSLg exports DISPLAY),
        # but the window is not hidden on this platform: starting the app pops
        # a real window on the user's desktop -- and, with no target configured,
        # a "startup failed" notice on top of it.  Only run this test when the
        # build was asked for it.
        if os.environ.get('SPB_GUI_SMOKE') != '1':
            print('    GUI launch test: skipped (set SPB_GUI_SMOKE=1 to run it)')
            return True
        if not (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):
            # Headless build hosts (CI, a WSL without WSLg): the packaged
            # binary is still valid, there is simply nothing to show.
            print('    GUI launch test: skipped (no display)')
            return True
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


# PyInstaller cannot cross-compile: each platform produces its own binary.
# The release channel ships the Windows EXE, but the source package carries
# this script so Linux/macOS users can build for their own platform.
IS_WINDOWS = sys.platform == 'win32'
EXE_SUFFIX = '.exe' if IS_WINDOWS else ''


def main() -> int:
    if not IS_WINDOWS:
        print('[platform] %s build (PyInstaller cannot cross-compile; this '
              'binary is for this platform only)' % sys.platform)
    parser = argparse.ArgumentParser(description='Package Server Protocol Bridge')
    parser.add_argument('--name', default=DEFAULT_NAME, help='EXE name')
    parser.add_argument('--console', action='store_true',
                        help='build a console-subsystem EXE (default; keeps a console window so cmd /c and PowerShell see CLI output -- the GUI detaches it on double-click)')
    parser.add_argument('--windowed', action='store_true',
                        help='build a GUI-subsystem EXE (no console; CLI output needs the parent-console attach, which can be invisible under cmd /c)')
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
        # The desktop shell is the Web UI in a native webview (pywebview).
        # The platform backend is picked at runtime, so PyInstaller cannot see
        # it; bundle the right one per platform plus the WebView2 assemblies
        # and the pythonnet runtime that ships inside the packages.
        '--collect-binaries', 'webview',
        '--collect-data', 'webview',
        '--hidden-import', 'cryptography',       # required for the encryption handshake
        '--hidden-import', 'mcauth3',            # Microsoft sign-in (optional at runtime)
    ]
    # Windows-only: cryptography's Rust extension links against the ABI3t DLL
    # name even on a standard (GIL) CPython 3.15 build.  CPython ships a
    # forwarding shim in abi3t-compat that maps python3t.dll to python315.dll;
    # without it the frozen EXE silently loses cryptography and cannot do the
    # AES handshake.  The version resource is a Windows concept too.
    if IS_WINDOWS:
        command += [
            '--collect-binaries', 'pythonnet',
            '--collect-binaries', 'clr_loader',
            '--hidden-import', 'clr',
            '--hidden-import', 'webview.platforms.winforms',
        ]
        abi3t_dll = Path(sys.base_prefix) / 'abi3t-compat' / 'python3t.dll'
        if abi3t_dll.is_file():
            command += ['--add-binary', '%s%s.' % (abi3t_dll, os.pathsep)]
        icon = ROOT / 'proxy' / 'assets' / 'icon.ico'
        if icon.is_file():
            command += ['--icon', str(icon)]
        version_file = ROOT / 'version_info.txt'
        if version_file.is_file():
            command += ['--version-file', str(version_file)]
    elif sys.platform == 'darwin':
        command += ['--hidden-import', 'webview.platforms.cocoa']
    else:
        # Linux: keep pywebview's GTK backend, but load PyGObject, GTK and
        # WebKitGTK from the system instead of bundling them.  They are system
        # packages (python3-gi + gir1.2-webkit2-4.1) and pulling them into the
        # single file adds about 50 MB of duplicated libraries, icons and ICU
        # data.  proxy.gui_shell.extend_system_paths() adds the distribution's
        # site-packages to sys.path at startup so ``import gi`` reaches the
        # installed PyGObject; with those packages absent the shell falls back
        # to the browser.  PyInstaller only ships stdlib modules the app
        # imports, so list the ones PyGObject needs from the frozen runtime.
        command += [
            '--hidden-import', 'webview.platforms.gtk',
            '--exclude-module', 'gi',
            '--exclude-module', 'gi.repository',
            '--hidden-import', 'pkgutil',
            '--hidden-import', '__future__',
            '--hidden-import', 'optparse',
        ]
    for module in EXCLUDES:
        command += ['--exclude-module', module]
    command.append(str(ROOT / 'main.py'))

    print('[1/3] running PyInstaller (onefile, no UPX/MPRESS)...')
    started = time.time()
    completed = subprocess.run(command, cwd=str(ROOT))
    if completed.returncode != 0:
        print('[failed] PyInstaller returned %d' % completed.returncode)
        return completed.returncode
    exe = DIST / (args.name + EXE_SUFFIX)
    if not exe.exists():
        print('[failed] %s was not produced' % exe)
        return 1
    print('  size: %s, built in %.0f s' % (human(exe.stat().st_size), time.time() - started))

    report = [
        '%s: %s' % ('EXE' if IS_WINDOWS else 'binary', exe),
        'platform: %s (%s)' % (sys.platform, 'x86_64' if sys.maxsize > 2**32 else 'x86'),
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
