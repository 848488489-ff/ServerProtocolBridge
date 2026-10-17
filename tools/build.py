"""一键打包: PyInstaller (onefile) -> UPX 压缩 -> MPRESS 压缩 -> 冒烟验证。

    python tools/build.py                 # 默认: 带控制台 + UPX + MPRESS
    python tools/build.py --no-mpress     # 只出 UPX 版
    python tools/build.py --windowed      # 无控制台版(纯 GUI)
    python tools/build.py --name 我的工具   # 自定义 EXE 名称

流程说明:
  1) PyInstaller 用 --upx-dir 把 python3x.dll、tcl/tk 等内部文件用 UPX 压缩;
  2) 再对生成的 EXE 本身做一次 UPX 压缩(失败会自动回退, 保留未压缩版);
  3) 额外用 MPRESS 压一份到 dist\\MPRESS\\, 作为备选分发包;
  4) 每个产物都会跑一次冒烟测试(启动 --version / --check), 不通过的产物会被丢弃。
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

# 打包时用不到的模块, 去掉可以明显减小体积
# 注意: 不要排除 distutils —— PyInstaller 的 hook-distutils 会把它别名到 setuptools._distutils,
# 目标名已在图里(被排除)就会直接报 ValueError 打包失败。
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
    """执行外部命令并捕获输出。

    Windows 控制台默认是 GBK(cp936), UPX / MPRESS 的输出是本地编码, 用 text 模式解码会抛
    UnicodeDecodeError, 因此这里一律用二进制捕获再手动解码, 并对无法识别的字节做替换。
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
    """跑一次 --version, 确认压缩后的 EXE 仍能启动。"""
    try:
        completed = run_capture([str(exe), '--version'], timeout=120)
    except Exception as exc:
        print('    冒烟测试异常: %s' % exc)
        return False
    output = ((completed.stdout or '') + (completed.stderr or ''))
    ok = completed.returncode == 0 and 'MCJS' in output
    print('    冒烟测试: %s' % ('通过' if ok else '失败'))
    if not ok:
        print('    returncode: %s' % completed.returncode)
        print('    输出: %s' % output[:300])
    return ok


def gui_smoke(exe: Path, seconds: float = 6.0) -> bool:
    """启动 GUI(窗口隐藏), 撑住若干秒说明 tcl/tk 等被压缩过的 DLL 仍然正常。"""
    startupinfo = None
    if os.name == 'nt':
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
    try:
        process = subprocess.Popen([str(exe)], startupinfo=startupinfo,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as exc:
        print('    GUI 启动测试异常: %s' % exc)
        return False
    time.sleep(seconds)
    alive = process.poll() is None
    if alive:
        process.terminate()
        try:
            process.wait(timeout=20)
        except Exception:
            process.kill()
    print('    GUI 启动测试: %s' % ('通过' if alive else '失败(进程提前退出)'))
    return alive


def build_mpress_folder(python: str, mpress: Path, report: list[str]) -> bool:
    """生成 MPRESS 压缩版(文件夹形式)。

    注意: MPRESS 会把 PyInstaller --onefile 挂在 EXE 尾部的归档当成 overlay 丢掉
    (13 MB -> 181 KB, 结果必然无法运行), 所以这里先打一个 --onedir 目录,
    再对目录里每个 .exe / .dll / .pyd 逐个压缩, 最后连带 zip 一起放到 dist。
    """
    stage = BUILD / 'mpress_onedir'
    app_root = stage / 'app'
    if stage.exists():
        shutil.rmtree(stage, ignore_errors=True)
    command = [
        python, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir',
        '--name', 'MCJS-Bridge', '--distpath', str(app_root),
        '--workpath', str(stage / 'work'), '--specpath', str(stage), '--console',
        '--collect-submodules', 'mcjs_proxy',
        '--hidden-import', 'tkinter', '--hidden-import', 'tkinter.filedialog',
        '--hidden-import', 'cryptography',
    ]
    for module in EXCLUDES:
        command += ['--exclude-module', module]
    command.append(str(ROOT / 'main.py'))
    if run(command).returncode != 0:
        print('  onedir 打包失败, 跳过 MPRESS 版')
        return False

    app_dir = app_root / 'MCJS-Bridge'
    launcher = app_dir / 'MCJS-Bridge.exe'
    if not launcher.exists():
        print('  没有找到 %s, 跳过 MPRESS 版' % launcher)
        return False

    before = sum(item.stat().st_size for item in app_dir.rglob('*') if item.is_file())
    targets = [item for item in app_dir.rglob('*')
               if item.is_file() and item.suffix.lower() in ('.exe', '.dll', '.pyd')]
    print('  onedir 原始体积: %s, 待压缩 PE 文件 %d 个' % (human(before), len(targets)))

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
        # MPRESS 对个别文件会拒绝或原样返回, 只要没变小就还原, 保证目录始终可用
        if path.exists() and path.stat().st_size < size_before:
            packed += 1
        else:
            shutil.copy2(backup, path)
    print('  MPRESS 实际压缩了 %d/%d 个文件' % (packed, len(targets)))

    if not gui_smoke(launcher):
        print('  MPRESS 后程序无法启动, 目录回退到未压缩版本')
        for path, backup in backups.items():
            shutil.copy2(backup, path)
        if not gui_smoke(launcher):
            print('  回退后依然无法启动, 放弃 MPRESS 版')
            return False

    for backup in backups.values():
        backup.unlink(missing_ok=True)

    after = sum(item.stat().st_size for item in app_dir.rglob('*') if item.is_file())
    target_dir = DIST / 'MPRESS-文件夹版'
    final_dir = target_dir / app_dir.name
    if final_dir.exists():
        shutil.rmtree(final_dir, ignore_errors=True)
    target_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(app_dir, final_dir)
    archive = Path(shutil.make_archive(str(target_dir / 'MCJS-Bridge-MPRESS'), 'zip',
                                       root_dir=str(target_dir), base_dir=app_dir.name))
    print('  MPRESS 后体积: %s, 压缩包: %s (%s)'
          % (human(after), archive.name, human(archive.stat().st_size)))
    report.append('MPRESS 版: %s (%s, zip %s)'
                  % (final_dir, human(after), human(archive.stat().st_size)))
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description='打包 MCJS 服务器协议转换')
    parser.add_argument('--name', default='MCJS-服务器协议转换', help='EXE 名称')
    parser.add_argument('--windowed', action='store_true', help='无控制台窗口的纯 GUI 版')
    parser.add_argument('--no-upx', action='store_true', help='不使用 UPX')
    parser.add_argument('--no-mpress', action='store_true', help='不检测/不使用 MPRESS')
    parser.add_argument('--mpress-folder', action='store_true',
                        help='额外生成 MPRESS 压缩版(onedir 文件夹 + zip), 单文件版无法用 MPRESS')
    parser.add_argument('--python', default=sys.executable, help='用于打包的 Python 解释器')
    args = parser.parse_args()

    upx_dir = None if args.no_upx else find_tool(UPX_CANDIDATES, 'upx.exe')
    upx = find_tool(UPX_CANDIDATES, 'upx.exe') if not args.no_upx else None
    mpress = None if args.no_mpress else find_tool(MPRESS_CANDIDATES, 'mpress.exe')

    if not args.no_upx and upx is None:
        print('[警告] 没有找到 UPX, 将只生成未压缩版本(可以稍后手动压缩)')
    if args.no_mpress:
        print('[提示] 已按参数要求跳过 MPRESS')
    elif mpress is None:
        print('[提示] 没有找到 MPRESS, 跳过 MPRESS 版')

    # 注意: 只删上一次的打包产物, 保留 dist 下的 certs/ 和 config.json ——
    # 证书一旦被删就要重新导入系统信任库, 配置也会丢。
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

    # 源码目录里已经有证书的话, 复制一份给 EXE 用, 这样浏览器信任一次就够
    source_certs = ROOT / 'certs'
    target_certs = DIST / 'certs'
    if source_certs.is_dir() and not target_certs.exists():
        shutil.copytree(source_certs, target_certs)

    command = [
        args.python, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile',
        '--name', args.name,
        '--distpath', str(DIST), '--workpath', str(BUILD), '--specpath', str(BUILD),
        '--console' if not args.windowed else '--windowed',
        '--collect-submodules', 'mcjs_proxy',
        '--hidden-import', 'tkinter', '--hidden-import', 'tkinter.filedialog',
        '--hidden-import', 'cryptography',       # 加密握手要用(可选依赖, 但没有它就没法代做)
    ]
    if upx_dir is not None:
        command += ['--upx-dir', str(upx_dir)]
    for module in EXCLUDES:
        command += ['--exclude-module', module]
    command.append(str(ROOT / 'main.py'))

    print('[1/5] PyInstaller 打包中...')
    started = time.time()
    completed = subprocess.run(command, cwd=str(ROOT))
    if completed.returncode != 0:
        print('[失败] PyInstaller 返回码 %d' % completed.returncode)
        return completed.returncode
    exe = DIST / ('%s.exe' % args.name)
    if not exe.exists():
        print('[失败] 没有生成 %s' % exe)
        return 1
    print('  原始体积: %s, 用时 %.0f 秒' % (human(exe.stat().st_size), time.time() - started))
    report = ['EXE: %s' % exe, '原始体积: %s' % human(exe.stat().st_size)]

    if upx is not None:
        print('[2/5] UPX 压缩 EXE...')
        backup = BUILD / 'unpacked.exe'
        shutil.copy2(exe, backup)
        result = run([str(upx), '--best', '--lzma', '--force', str(exe)],
                     capture_output=True, text=True)
        packed_ok = result.returncode == 0 and smoke_test(exe)
        if packed_ok:
            print('  UPX 后体积: %s' % human(exe.stat().st_size))
            report.append('UPX 压缩: %s' % human(exe.stat().st_size))
        else:
            print('  UPX 压缩后无法运行, 已回退到未压缩版本')
            print('  %s' % (result.stdout or '')[:300])
            shutil.copy2(backup, exe)
            report.append('UPX 压缩: 失败(已回退)')
    else:
        print('[2/5] 跳过 UPX')

    if mpress is not None and args.mpress_folder:
        print('[3/5] 生成 MPRESS 版(onedir 文件夹, 逐个 PE 压缩)...')
        build_mpress_folder(args.python, mpress, report)
    elif mpress is not None:
        print('[3/5] 跳过 MPRESS 单文件版:')
        print('      MPRESS 不认识 PyInstaller --onefile 的尾部归档, 会把它当 overlay 丢掉')
        print('      (实测 13.2 MB -> 181 KB, 压完无法运行)。需要 MPRESS 版请加 --mpress-folder。')
    else:
        print('[3/5] 没有找到 MPRESS, 跳过')

    print('[4/5] 最终冒烟测试(--check 会生成证书并测试目标服务器连通性)...')
    final_ok = smoke_test(exe)
    if not final_ok:
        print('[失败] 最终产物无法启动')
        return 1
    selftest = run_capture([str(exe), '--selftest'], timeout=120)
    print('  --- 自检 ---')
    print('  ' + (selftest.stdout or '').strip().replace('\n', '\n  '))
    if selftest.returncode != 0:
        print('[失败] 自检没通过: 加密库(cryptography)或图形界面没打进包里')
        print('  ' + (selftest.stderr or '').strip())
        return 1
    check = run_capture([str(exe), '--check', '--log-level', 'warn'], timeout=240)
    print('  --check 返回码 %d (1 表示目标服务器不可达, 不影响程序本身)' % check.returncode)

    print('[5/5] 汇总')
    report.append('SHA256: %s' % sha256(exe))
    text = '\n'.join(report)
    (DIST / 'build-report.txt').write_text(text + '\n', encoding='utf-8')
    print(text)
    print('\n产物目录: %s' % DIST)
    return 0


if __name__ == '__main__':
    sys.exit(main())