#!/usr/bin/env python3
"""MCJS 服务器协议转换 —— 程序入口。

直接运行(或双击 EXE)会打开图形界面; 加 --no-gui 则以命令行方式运行。

    python main.py
    python main.py --no-gui --target mc.hypixel.net:25565
    python main.py --check
"""

from __future__ import annotations

import sys

CLI_FLAGS = ('--no-gui', '--cli', '--check', '--install-cert', '--version', '--help', '-h')


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
    except ImportError as exc:  # 没有 tkinter 时退回命令行
        print('无法加载图形界面(%s), 已切换到命令行模式。' % exc)
        print('提示: Windows 请安装带 tkinter 的 Python; Linux 需安装 python3-tk。\n')
        from mcjs_proxy.cli import main as cli_main

        return cli_main(argv)
    return gui_main()


if __name__ == '__main__':
    sys.exit(main())