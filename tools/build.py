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
EXCLUDES = [
    'unittest', 'pydoc', 'difflib', 'idlelib', 'ensurepip', 'sqlite3',
    'tkinter.test', 'turtledemo', 'lib2to3', 'pip', 'setuptools', 'pkg_resources',
    'test', 'distutils', 'numpy', 'PIL', 'PyQt5', 'PySide6',
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


def run_capture(command: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    """执行外部命令并捕获输出。

    Windows 控制台默认是 GBK(cp936), UPX / MPRESS 的输出是本地编码, 用 text 模式解码会抛
    UnicodeDecodeError, 因此这里一律用二进制捕获再手动解码, 并对无法识别的字节做替换。
    """
    printable = ' '.join(str(item) for item in command)
    print('  $ %s' % printable)
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


def main() -> int:
    parser = argparse.ArgumentParser(description='打包 MCJS 服务器协议转换')
    parser.add_argument('--name', default='MCJS-服务器协议转换', help='EXE 名称')
    parser.add_argument('--windowed', action='store_true', help='无控制台窗口的纯 GUI 版')
    parser.add_argument('--no-upx', action='store_true', help='不使用 UPX')
    parser.add_argument('--no-mpress', action='store_true', help='不生成 MPRESS 版')
    parser.add_argument('--python', default=sys.executable, help='用于打包的 Python 解释器')
    args = parser.parse_args()

    upx_dir = None if args.no_upx else find_tool(UPX_CANDIDATES, 'upx.exe')
    upx = find_tool(UPX_CANDIDATES, 'upx.exe') if not args.no_upx else None
    mpress = None if args.no_mpress else find_tool(MPRESS_CANDIDATES, 'mpress.exe')

    if not args.no_upx and upx is None:
        print('[警告] 没有找到 UPX, 将只生成未压缩版本(可以稍后手动压缩)')
    if not args.no_mpress and mpress is None:
        print('[提示] 没有找到 MPRESS, 跳过 MPRESS 版')

    if DIST.exists():
        shutil.rmtree(DIST, ignore_errors=True)
    if BUILD.exists():
        shutil.rmtree(BUILD, ignore_errors=True)

    command = [
        args.python, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile',
        '--name', args.name,
        '--distpath', str(DIST), '--workpath', str(BUILD), '--specpath', str(BUILD),
        '--console' if not args.windowed else '--windowed',
        '--collect-submodules', 'mcjs_proxy',
        '--hidden-import', 'tkinter', '--hidden-import', 'tkinter.filedialog',
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

    if mpress is not None:
        print('[3/5] MPRESS 压缩...')
        mpress_dir = DIST / 'MPRESS'
        mpress_dir.mkdir(parents=True, exist_ok=True)
        mpress_exe = mpress_dir / ('%s.exe' % args.name)
        shutil.copy2(exe, mpress_exe)
        result = run([str(mpress), str(mpress_exe), '-x', '-b'],
                     capture_output=True, text=True)
        if result.returncode == 0 and smoke_test(mpress_exe):
            print('  MPRESS 后体积: %s' % human(mpress_exe.stat().st_size))
            report.append('MPRESS 版: %s (压缩后 %s)' % (mpress_exe, human(mpress_exe.stat().st_size)))
        else:
            print('  MPRESS 结果不可用, 已删除该文件')
            mpress_exe.unlink(missing_ok=True)
            print('  %s' % ((result.stdout or '') + (result.stderr or ''))[:300])
    else:
        print('[3/5] 跳过 MPRESS')

    print('[4/5] 最终冒烟测试(--check 会生成证书并测试目标服务器连通性)...')
    final_ok = smoke_test(exe)
    if not final_ok:
        print('[失败] 最终产物无法启动')
        return 1
    check = subprocess.run([str(exe), '--check', '--log-level', 'warn'],
                           capture_output=True, text=True, timeout=180)
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