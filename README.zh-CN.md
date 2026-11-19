# Server Protocol Bridge

**[English](README.md) | [中文](README.zh-CN.md)**

> **这个版本还不够成熟，不推荐在装有严格反作弊的服务器上使用。**

`Server Protocol Bridge` 把普通 Minecraft **Java 版** TCP 服务器转换为本地
`wss://` / `ws://` 端点，让基于浏览器的 **Eaglercraft** 客户端（它不会说原生
TCP 协议）能连接进去。客户端全程不涉及 JVM。

## 功能

- 在本地监听 `wss://`（TLS，自签 CA）/ `ws://` 端点。
- 对浏览器客户端说 **Eaglercraft 握手方言 v1–v5**（按连接协商，含 v5
  能力位与扩展表）。
- 在 **Eaglercraft 线格式** 与 **原生 Minecraft 协议**（VarInt 帧、压缩阈值、
  登录/游戏阶段）之间翻译。
- **代答服务器的加密请求**：用服务器公钥 RSA 加密随机共享密钥，选择已认证
  账户时向 Mojang 会话服务注册 join，随后双向切换 AES-128-CFB8。
- 本地应答浏览器客户端的 **服务器列表 MOTD** 查询。
- 通过 **SRV 记录** 解析目标、维护 **状态缓存**、转发资源包（可配置）。
- 跨平台：Windows EXE、Android APK（Chaquopy）、Linux（AppImage/deb/rpm），
  另有 Web UI 与原生窗口外壳。

> **全程不使用任何 Java。** Android 应用层用 **Kotlin** 编写（唯一新增依赖是
> `kotlin-stdlib`）；Chaquopy 用于嵌入 Python 运行时，不是 Java 依赖。项目里
> 没有任何 Java 源文件，也没有 Java 库。界面语言默认 **auto**（跟随系统），
> Android 外壳的通知文本、渠道描述与权限提示会跟随 Web UI 里选择的语言。

## 快速开始

```bash
pip install -r requirements.txt
python main.py            # 打开 Web UI / 原生窗口
python main.py --no-gui --target play.example.net --port 8443
```

或直接运行 `dist/` 里的打包产物（先用 `tools/build.py` 构建）。

## 配置

配置在 `config.json`（首次运行自动生成默认值，且被 git 忽略——它是机器本地
配置）。常用键：

| 键 | 含义 |
|---|---|
| `listen_host` / `wss_port` / `ws_port` | 本地端点地址与端口 |
| `target` | 要转发的原生 TCP 服务器 |
| `eagler_translate` | 启用 Eaglercraft ↔ 原生翻译 |
| `login_ack` | 应答 1.20.2+ 的登录确认包 |
| `resource_pack_mode` | `forward` / `prompt` / `ignore` |
| `language` | `auto`（跟随系统，默认）、`en`、`zh` |
| `startup_notice` | 启动时显示"还不够成熟"提示 |

## 构建

- **Windows**：`tools/build.py`（PyInstaller）→ `dist/Server Protocol Bridge.exe`
- **Android**：`android/` Gradle 工程（Kotlin + Chaquopy）→ `app-release.apk`
- **Linux**：WSL2 内 `tools/build_wsl.sh`

## 测试

```bash
python -m pytest tests/ -q
```

## 目录结构

```
proxy/       桥接核心：协议翻译、WebSocket/TCP 泵、Web UI、多语言
tools/       构建、导出源码、许可证与发布辅助
tests/       Pytest 套件（协议、翻译、加密、API、Web UI）
web/         项目更新/下载网站（Cloudflare Pages）
android/     Kotlin Android 包装（Gradle + Chaquopy）
```

## 许可证

见 [LICENSE](LICENSE)。第三方声明见
[THIRD_PARTY_NOTICES.txt](THIRD_PARTY_NOTICES.txt)。
