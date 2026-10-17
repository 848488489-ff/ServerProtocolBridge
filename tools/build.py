"""One-shot packaging: PyInstaller (onefile) -> UPX -> MPRESS -> smoke verification.

    python tools/build.py                 # default: console build + UPX + MPRESS
    python tools/build.py --no-mpress     # UPX build only
    python tools/build.py --windowed      # no console window (pure GUI)
    python tools/build.py --name MyTool   # custom EXE name

Pipeline:
  1) PyInstaller with --upx-dir compresses internal files such as python3x.dll and tcl/tk with UPX;
  2) the generated EXE itself gets a second UPX pass (on failure it rolls back and keeps the
     uncompressed build);
  3) an extra MPRESS-compressed copy is written to dist\\MPRESS-folder\\ as an alternative
     distribution;
  4) every artifact is smoke-tested (startup --version / --check); artifacts that fail are dropped.
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

# Default name of the produced EXE: it is the name a user sees and double-clicks,
# so it is the localized program name.
DEFAULT_NAME = '服务器协议转换'
# What the smoke test looks for in the --version output (the program name in
# whichever UI language the EXE ends up running with).
SMOKE_NAMES = ('Server Protocol Bridge', '服务器协议转换')

# Modules that are never needed at runtime; excluding them shrinks the build noticeably.
# NOTE: do not exclude distutils -- PyInstaller's hook-distutils aliases it to setuptools._distutils,
# and with the target name already excluded from the graph the build fails with a ValueError.
EXCLUDES = [
    'unittest', 'pydoc', 'difflib', 'idlelib', 'ensurepip', 'sqlite3',
    'tkinter.test', 'turtledemo', 'lib2to3', 'pip', 'setuptools', 'pkg_resources',
    'test', 'numpy', 'PIL', 'PyQt5', 'PySide6',
]

UPX_CANDIDATES = [
    Path(r'D:\upx-5.2.1-win64'), Path(r'D:\upx'), Path(r'C:\Program Files\upx'),
]
MPRESS_CANDIDATES = [Path(r'D:\MPRESS'), Path(r'C:\MPRESS')]


def find_tool(candidates: list[Path], exe_name: str) -> Path | None:
    found = shutil.which(exe_name)
    if found:
        return Path(found)
    for folder in candidates:
        candidate = folder / exe_name
        if candidate.exists():
            return candidate
    return None


def human(size: int) -> str:
    return '%.2f MB' % (size / 1024 / 1024)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
    printable = ' '.join(str(item) for item in command)
    print('  $ %s' % printable)
    return subprocess.run(command, **kwargs)


def run_capture(command: list[str], timeout: int = 300, quiet: bool = False) -> subprocess.CompletedProcess:
    """Run an external command and capture its output.

    The Windows console defaults to GBK (cp936) and UPX / MPRESS print in the local encoding, so
    decoding in text mode raises UnicodeDecodeError. Everything is therefore captured as bytes and
    decoded manually, replacing any undecodable bytes.
    """
    if not quiet:
        print('  $ %s' % ' '.join(str(item) for item in command))
    completed = subprocess.run(command, capture_output=True, timeout=timeout)
    encoding = 'utf-8'
    if os.name == 'nt':
        encoding = locale.getpreferredencoding(False) or 'gbk'
    for name in ('stdout', 'stderr'):
        raw = getattr(completed, name) or b''
        setattr(completed, name, raw.decode(encoding, errors='replace'))
    return completed


def smoke_test(exe: Path) -> bool:
    """Run --version once to confirm the compressed EXE still starts."""
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
    """Start the GUI (window hidden) and keep it alive for a few seconds; that proves the
    UPX-compressed DLLs such as tcl/tk still load and run."""
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
        process.terminate()
        try:
            process.wait(timeout=20)
        except Exception:
            process.kill()
    print('    GUI launch test: %s' % ('passed' if alive else 'failed (process exited early)'))
    return alive


def build_mpress_folder(python: str, mpress: Path, report: list[str], name: str) -> bool:
    """Build the MPRESS-compressed variant (folder form).

    NOTE: MPRESS treats the archive PyInstaller --onefile appends to the EXE tail as an overlay and
    drops it (13 MB -> 181 KB, the result can never run), so this builds a --onedir tree first,
    compresses every .exe / .dll / .pyd inside it one by one, and finally ships it (zip included)
    into dist.
    """
    stage = BUILD / 'mpress_onedir'
    app_root = stage / 'app'
    if stage.exists():
        shutil.rmtree(stage, ignore_errors=True)
    command = [
        python, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir',
        '--name', name, '--distpath', str(app_root),
        '--workpath', str(stage / 'work'), '--specpath', str(stage), '--console',
        '--collect-submodules', 'proxy',
        '--collect-all', 'uvicorn',              # uvicorn imports its protocol / loop /
        '--collect-all', 'websockets',           # lifespan modules dynamically, so the
        '--hidden-import', 'httptools',          # freezer has to be told about them
        '--hidden-import', 'tkinter', '--hidden-import', 'tkinter.filedialog',
        '--hidden-import', 'cryptography',
    ]
    for module in EXCLUDES:
        command += ['--exclude-module', module]
    command.append(str(ROOT / 'main.py'))
    if run(command).returncode != 0:
        print('  onedir build failed, skipping the MPRESS variant')
        return False

    app_dir = app_root / name
    launcher = app_dir / ('%s.exe' % name)
    if not launcher.exists():
        print('  %s not found, skipping the MPRESS variant' % launcher)
        return False

    before = sum(item.stat().st_size for item in app_dir.rglob('*') if item.is_file())
    targets = [item for item in app_dir.rglob('*')
               if item.is_file() and item.suffix.lower() in ('.exe', '.dll', '.pyd')]
    print('  original onedir size: %s, PE files to compress: %d' % (human(before), len(targets)))

    backups: dict[Path, Path] = {}
    packed = 0
    for path in targets:
        backup = path.with_name(path.name + '.orig')
        shutil.copy2(path, backup)
        backups[path] = backup
        size_before = path.stat().st_size
        try:
            run_capture([str(mpress), str(path)], quiet=True)
        except Exception:
            pass
        # MPRESS refuses or returns some files unchanged; restore anything that did not shrink,
        # so the tree stays usable no matter what
        if path.exists() and path.stat().st_size < size_before:
            packed += 1
        else:
            shutil.copy2(backup, path)
    print('  MPRESS actually compressed %d/%d files' % (packed, len(targets)))

    if not gui_smoke(launcher):
        print('  the app no longer starts after MPRESS, restoring the uncompressed tree')
        for path, backup in backups.items():
            shutil.copy2(backup, path)
        if not gui_smoke(launcher):
            print('  still not starting after restore, giving up on the MPRESS variant')
            return False

    for backup in backups.values():
        backup.unlink(missing_ok=True)

    after = sum(item.stat().st_size for item in app_dir.rglob('*') if item.is_file())
    target_dir = DIST / 'MPRESS-folder'
    final_dir = target_dir / app_dir.name
    if final_dir.exists():
        shutil.rmtree(final_dir, ignore_errors=True)
    target_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(app_dir, final_dir)
    archive = Path(shutil.make_archive(str(target_dir / ('%s-MPRESS' % name)), 'zip',
                                       root_dir=str(target_dir), base_dir=app_dir.name))
    print('  size after MPRESS: %s, archive: %s (%s)'
          % (human(after), archive.name, human(archive.stat().st_size)))
    report.append('MPRESS build: %s (%s, zip %s)'
                  % (final_dir, human(after), human(archive.stat().st_size)))
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description='Package Server Protocol Bridge')
    parser.add_argument('--name', default=DEFAULT_NAME, help='EXE name')
    parser.add_argument('--windowed', action='store_true', help='pure GUI build without a console window')
    parser.add_argument('--no-upx', action='store_true', help='do not use UPX')
    parser.add_argument('--no-mpress', action='store_true', help='do not detect / use MPRESS')
    parser.add_argument('--mpress-folder', action='store_true',
                        help='also build an MPRESS variant (onedir folder + zip); '
                             'single-file builds cannot be MPRESS-compressed')
    parser.add_argument('--python', default=sys.executable, help='Python interpreter used for packaging')
    args = parser.parse_args()

    upx_dir = None if args.no_upx else find_tool(UPX_CANDIDATES, 'upx.exe')
    upx = find_tool(UPX_CANDIDATES, 'upx.exe') if not args.no_upx else None
    mpress = None if args.no_mpress else find_tool(MPRESS_CANDIDATES, 'mpress.exe')

    if not args.no_upx and upx is None:
        print('[warning] UPX not found, building only the uncompressed version '
              '(you can compress it manually later)')
    if args.no_mpress:
        print('[info] MPRESS skipped as requested')
    elif mpress is None:
        print('[info] MPRESS not found, skipping the MPRESS variant')

    # NOTE: only previous build artifacts are deleted; certs/ and config.json under dist are kept --
    # once the certificates are gone they must be re-imported into the OS trust store, and the
    # configuration would be lost too.
    keep = {DIST / 'certs', DIST / 'config.json'}
    if DIST.exists():
        for item in DIST.iterdir():
            if item in keep:
                continue
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
            else:
                item.unlink(missing_ok=True)
    if BUILD.exists():
        shutil.rmtree(BUILD, ignore_errors=True)

    # If the source tree already contains certificates, copy them next to the EXE, so the browser
    # only has to trust them once
    source_certs = ROOT / 'certs'
    target_certs = DIST / 'certs'
    if source_certs.is_dir() and not target_certs.exists():
        shutil.copytree(source_certs, target_certs)

    command = [
        args.python, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile',
        '--name', args.name,
        '--distpath', str(DIST), '--workpath', str(BUILD), '--specpath', str(BUILD),
        '--console' if not args.windowed else '--windowed',
        '--collect-submodules', 'proxy',
        '--collect-all', 'uvicorn',              # uvicorn imports its protocol / loop /
        '--collect-all', 'websockets',           # lifespan modules dynamically, so the
        '--hidden-import', 'httptools',          # freezer has to be told about them
        '--hidden-import', 'tkinter', '--hidden-import', 'tkinter.filedialog',
        '--hidden-import', 'cryptography',       # required for the encryption handshake
                                                 # (optional dependency, but without it we cannot relay it)
    ]
    if upx_dir is not None:
        command += ['--upx-dir', str(upx_dir)]
    for module in EXCLUDES:
        command += ['--exclude-module', module]
    command.append(str(ROOT / 'main.py'))

    print('[1/5] running PyInstaller...')
    started = time.time()
    completed = subprocess.run(command, cwd=str(ROOT))
    if completed.returncode != 0:
        print('[failed] PyInstaller returned %d' % completed.returncode)
        return completed.returncode
    exe = DIST / ('%s.exe' % args.name)
    if not exe.exists():
        print('[failed] %s was not produced' % exe)
        return 1
    print('  original size: %s, built in %.0f s' % (human(exe.stat().st_size), time.time() - started))
    report = ['EXE: %s' % exe, 'original size: %s' % human(exe.stat().st_size)]

    if upx is not None:
        print('[2/5] compressing the EXE with UPX...')
        backup = BUILD / 'unpacked.exe'
        shutil.copy2(exe, backup)
        result = run([str(upx), '--best', '--lzma', '--force', str(exe)],
                     capture_output=True, text=True)
        packed_ok = result.returncode == 0 and smoke_test(exe)
        if packed_ok:
            print('  size after UPX: %s' % human(exe.stat().st_size))
            report.append('UPX compression: %s' % human(exe.stat().st_size))
        else:
            print('  the UPX-compressed EXE no longer runs, rolled back to the uncompressed build')
            print('  %s' % (result.stdout or '')[:300])
            shutil.copy2(backup, exe)
            report.append('UPX compression: failed (rolled back)')
    else:
        print('[2/5] skipping UPX')

    if mpress is not None and args.mpress_folder:
        print('[3/5] building the MPRESS variant (onedir folder, per-file PE compression)...')
        build_mpress_folder(args.python, mpress, report, args.name)
    elif mpress is not None:
        print('[3/5] skipping the single-file MPRESS build:')
        print('      MPRESS does not understand the archive PyInstaller --onefile appends to the EXE')
        print('      and drops it as an overlay (measured 13.2 MB -> 181 KB, the result never runs).')
        print('      Pass --mpress-folder if you need an MPRESS build.')
    else:
        print('[3/5] MPRESS not found, skipping')

    print('[4/5] final smoke test (--check generates certificates and tests connectivity to the target server)...')
    final_ok = smoke_test(exe)
    if not final_ok:
        print('[failed] the final artifact does not start')
        return 1
    selftest = run_capture([str(exe), '--selftest'], timeout=120)
    print('  --- self-test ---')
    print('  ' + (selftest.stdout or '').strip().replace('\n', '\n  '))
    if selftest.returncode != 0:
        print('[failed] self-test did not pass: the crypto library (cryptography) or the GUI is missing from the package')
        print('  ' + (selftest.stderr or '').strip())
        return 1
    check = run_capture([str(exe), '--check', '--log-level', 'warn'], timeout=240)
    print('  --check returned %d (1 means the target server was unreachable, the program itself is fine)'
          % check.returncode)

    print('[5/5] summary')
    report.append('SHA256: %s' % sha256(exe))
    text = '\n'.join(report)
    (DIST / 'build-report.txt').write_text(text + '\n', encoding='utf-8')
    print(text)
    print('\nartifacts directory: %s' % DIST)
    return 0


if __name__ == '__main__':
    sys.exit(main())
