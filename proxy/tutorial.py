"""Usage tutorials for MCP and CLI, opened with the system's default app.

The tutorials are plain Markdown embedded here rather than read from a file so
the packaged EXE does not need to ship separate documents.  ``open_tutorial``
writes the selected language's text to a temporary file and asks the OS to open
it with the default handler, so it works on Windows (``os.startfile``), macOS
(``open``) and Linux (``xdg-open``) without any extra dependency.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile

# ---------------------------------------------------------------------------
# Tutorial texts.  Each entry is a dict keyed by language code ('en'/'zh').
# Keep them short but complete: a reader should be able to follow along.
# ---------------------------------------------------------------------------

MCP_TUTORIAL: dict[str, dict[str, str]] = {
    'en': {
        'title': 'MCP (Model Context Protocol) Usage',
        'body': """# MCP (Model Context Protocol) Usage

The program exposes a Model Context Protocol server on the Web UI listener.
An MCP client (an AI assistant, an IDE, or any JSON-RPC 2.0 client) can connect
to the **/mcp** endpoint and drive the program directly.

## 1. Endpoint

The endpoint URL is shown on the settings page under "MCP endpoint" and is also
returned by the `status` MCP tool. It looks like:

    http://127.0.0.1:8765/mcp

## 2. Security

* **Loopback access** (127.0.0.1) needs no key. Anyone on the local machine can
  call the endpoint.
* **Non-loopback access** (0.0.0.0 or a LAN address) requires an **MCP key**.
  Set one on the settings page ("MCP key", at least 8 characters). If the Web UI
  password is enabled but no MCP key is set, remote MCP calls are refused.

## 3. Connecting a client

Present the key as a bearer token in the `Authorization` header:

    Authorization: Bearer <your-mcp-key>

For Streamable HTTP transports, send the key as an `MCP-Protocol-Version` or
`Authorization` header depending on the client.

## 4. Available tools

The server exposes tools for status, configuration (including appearance
personalization, the path-route table and suffix routing), service control,
logs, accounts,
certificates, update checks, Web UI restart, UI preferences (theme, language,
appearance), password and MCP key management, config reset, config reload from
disk, the log buffer size, and reading or opening the usage tutorials. Call
them over JSON-RPC 2.0:

    {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
     "params": {"name": "status", "arguments": {}}}

## 5. Resources and prompts

* Resources: `logs`, `status`, `config`, `about`, `mcp`
* Prompts: `diagnose`, `microsoft-signin`, `configure-forwarding`, `secure-remote`

Use `resources/read` and `prompts/get` to consume them.
""",
    },
    'zh': {
        'title': 'MCP（模型上下文协议）使用教程',
        'body': """# MCP（模型上下文协议）使用教程

程序在 Web UI 监听器上提供了一个模型上下文协议（MCP）服务器。任何 MCP
客户端（AI 助手、IDE 或任何 JSON-RPC 2.0 客户端）都可以连接 **/mcp** 端点，
直接操控程序。

## 1. 端点地址

端点地址显示在设置页的“MCP 端点”一栏，也可通过 `status` MCP 工具获取。形如：

    http://127.0.0.1:8765/mcp

## 2. 安全

* **回环访问**（127.0.0.1）无需密钥，本机任何进程都能调用端点。
* **非回环访问**（0.0.0.0 或局域网地址）需要 **MCP 密钥**。请在设置页设置
  （“MCP 密钥”，至少 8 个字符）。若已启用 Web UI 密码但未设 MCP 密钥，
  远程 MCP 调用会被拒绝。

## 3. 连接客户端

在 `Authorization` 请求头中以 Bearer 令牌形式出示密钥：

    Authorization: Bearer <你的MCP密钥>

Streamable HTTP 传输方式下，请根据客户端要求以 `MCP-Protocol-Version` 或
`Authorization` 请求头携带密钥。

## 4. 可用工具

服务器提供状态、配置（含外观个性化、路径路由表和路径后缀直连）、服务控制、日志、账号、
证书、更新检查、Web UI 重启、界面偏好（主题/语言/外观）、密码与 MCP 密钥
管理、配置重置、从磁盘重新加载配置、日志缓冲区大小调整，以及读取或打开
使用教程等工具。用 JSON-RPC 2.0 调用：

    {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
     "params": {"name": "status", "arguments": {}}}

## 5. 资源与提示词

* 资源：`logs`、`status`、`config`、`about`、`mcp`
* 提示词：`diagnose`、`microsoft-signin`、`configure-forwarding`、`secure-remote`

用 `resources/read` 和 `prompts/get` 使用它们。
""",
    },
}

CLI_TUTORIAL: dict[str, dict[str, str]] = {
    'en': {
        'title': 'Command Line Usage',
        'body': """# Command Line Usage

The program runs in command line mode when you pass a CLI flag. The most useful
commands are shown below. Run `--help` for the full list.

## Basic

    "Server Protocol Bridge.exe" --no-gui --target play.example.net --port 8443

* `--no-gui` – run in command line mode (no window).
* `--target HOST` – forward target, resolved via SRV if no port is given.
* `--port PORT` – wss:// listen port (default 8443).

## Common flags

* `--listen HOST` – listen address (default 127.0.0.1).
* `--account NAME` – use a saved account for this run.
* `--language en|zh` – UI language.
* `--log-level debug|info|warn|error` – log verbosity.
* `--check` – check the certificate and connectivity, then exit.
* `--version` – print the version and exit.
* `--help` – print all options and exit.

## Examples

    # Forward with logging to the console
    "Server Protocol Bridge.exe" --no-gui --target 127.0.0.1:25565 --log-level debug

    # Check connectivity only
    "Server Protocol Bridge.exe" --check

    # Use a specific config file
    "Server Protocol Bridge.exe" --config my-config.json --no-gui
""",
    },
    'zh': {
        'title': '命令行使用教程',
        'body': """# 命令行使用教程

传入 CLI 标志时程序以命令行模式运行。最常用的命令如下，完整列表请用
`--help` 查看。

## 基本用法

    "Server Protocol Bridge.exe" --no-gui --target play.example.net --port 8443

* `--no-gui` – 以命令行模式运行（不弹窗口）。
* `--target HOST` – 转发目标，不带端口时按 SRV 解析。
* `--port PORT` – wss:// 监听端口（默认 8443）。

## 常用参数

* `--listen HOST` – 监听地址（默认 127.0.0.1）。
* `--account NAME` – 本次运行使用的已保存账号。
* `--language en|zh` – 界面语言。
* `--log-level debug|info|warn|error` – 日志级别。
* `--check` – 检查证书与连通性后退出。
* `--version` – 打印版本后退出。
* `--help` – 打印全部参数后退出。

## 示例

    # 转发并在控制台输出日志
    "Server Protocol Bridge.exe" --no-gui --target 127.0.0.1:25565 --log-level debug

    # 仅检查连通性
    "Server Protocol Bridge.exe" --check

    # 使用指定配置文件
    "Server Protocol Bridge.exe" --config my-config.json --no-gui
""",
    },
}


def _language() -> str:
    """Active UI language ('en' or 'zh'), matching the running interface."""
    try:
        from .i18n import get_language

        code = get_language()
        return code if code in ('en', 'zh') else 'en'
    except Exception:
        return 'en'


def tutorial(kind: str, language: str | None = None) -> dict:
    """Return ``{'title', 'body'}`` for a tutorial in the given language.

    *kind* is ``'mcp'`` or ``'cli'``; *language* is ``'en'``/``'zh'`` and falls
    back to the active UI language when omitted.
    """
    if kind == 'cli':
        table = CLI_TUTORIAL
    else:
        table = MCP_TUTORIAL
    lang = language if language in ('en', 'zh') else _language()
    entry = table.get(lang) or table['en']
    return {'kind': kind, 'language': lang, **entry}


def open_tutorial(kind: str, language: str | None = None) -> str:
    """Write the tutorial to a temp file and open it with the default app.

    Returns the path of the file that was opened.  Raises ``OSError`` /
    ``RuntimeError`` when no handler can be found.
    """
    info = tutorial(kind, language)
    ext = '.md'
    fd, path = tempfile.mkstemp(suffix=ext, prefix='spb-tutorial-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            handle.write(info['body'])
    except Exception:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise
    try:
        _open_with_default_app(path)
    except Exception:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise
    return path


def _open_with_default_app(path: str) -> None:
    """Open *path* with the OS default handler on Windows/macOS/Linux."""
    if sys.platform.startswith('win'):
        os.startfile(path)  # type: ignore[attr-defined]
        return
    if sys.platform == 'darwin':
        subprocess.Popen(['open', path])
        return
    if sys.platform.startswith('linux'):
        subprocess.Popen(['xdg-open', path])
        return
    raise RuntimeError('no default application handler on %s' % sys.platform)
