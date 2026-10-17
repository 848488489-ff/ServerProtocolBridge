"""分步提交脚本: 每个模块一个 commit, 便于回溯。

    py -3.14 tools\\commit_steps.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

STEPS = [
    ('feat: 实现 RFC6455 WebSocket 帧编解码与握手', ['mcjs_proxy/wsproto.py']),
    ('feat: 实现 SRV 解析与目标服务器连通性探测', ['mcjs_proxy/resolver.py']),
    ('feat: 实现配置读写、地址解析与校验', ['mcjs_proxy/config.py']),
    ('feat: 实现 WebSocket 到 TCP 转发核心', ['mcjs_proxy/proxy.py']),
    ('feat: 实现 tkinter 图形界面', ['mcjs_proxy/gui.py']),
    ('feat: 实现命令行模式与程序入口', ['mcjs_proxy/cli.py', 'main.py']),
    ('test: 添加自检测试(证书握手 / 帧编解码 / 端到端转发)', ['tests/test_all.py']),
    ('build: 添加 PyInstaller + UPX + MPRESS 打包脚本', ['tools/build.py', 'tools/build.bat', 'start.bat']),
    ('docs: 编写 README、配置示例与依赖说明', ['README.md', 'config.example.json', 'requirements.txt']),
]


def git(*args: str) -> int:
    return subprocess.run(['git', *args], cwd=str(ROOT)).returncode


def main() -> int:
    for message, files in STEPS:
        existing = [item for item in files if (ROOT / item).exists()]
        if not existing:
            print('[跳过] 文件不存在: %s' % ', '.join(files))
            continue
        if git('add', '--', *existing) != 0:
            print('[失败] git add: %s' % ', '.join(existing))
            return 1
        staged = subprocess.run(['git', 'diff', '--cached', '--quiet'], cwd=str(ROOT)).returncode
        if staged == 0:
            print('[跳过] 无改动: %s' % message)
            continue
        if git('commit', '-q', '-m', message) != 0:
            print('[失败] git commit: %s' % message)
            return 1
        print('[提交] %s' % message)

    print('\n--- 提交历史 ---')
    subprocess.run(['git', 'log', '--oneline'], cwd=str(ROOT))
    print('--- 未跟踪/未提交 ---')
    subprocess.run(['git', 'status', '--short'], cwd=str(ROOT))
    return 0


if __name__ == '__main__':
    sys.exit(main())