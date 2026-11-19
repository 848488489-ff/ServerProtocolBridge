# Server Protocol Bridge

**[English](README.md) | [Chinese](README.zh-CN.md)**

> **This build is not mature yet; it is not recommended on servers with strict
> anti-cheat.**

`Server Protocol Bridge` turns a plain vanilla Minecraft **Java Edition** TCP
server into a local `wss://` / `ws://` endpoint, so a browser-based
**Eaglercraft** client (which cannot speak the native TCP protocol) can join it.
The JVM is not involved on the client side at all.

## What it does

- Listens on a local `wss://` (TLS, self-signed CA) / `ws://` endpoint.
- Speaks the **Eaglercraft handshake dialects v1–v5** to the browser client
  (negotiated per connection, including v5 capability bits and extensions).
- Translates between the **Eaglercraft wire format** and the **vanilla Minecraft
  protocol** (VarInt framing, compression threshold, login/play phases).
- **Answers the server's encryption request on the client's behalf**: a random
  shared secret is RSA-encrypted with the server's public key, the session is
  registered with the Mojang join service when an authenticated account is
  selected, and both directions switch to AES-128-CFB8.
- Answers the browser client's **server-list MOTD** queries locally.
- Resolves the target through **SRV records**, keeps a **status cache** and
  forwards resource packs (configurable).
- Cross-platform: Windows EXE, Android APK (Chaquopy), Linux
  (AppImage/deb/rpm), plus a Web UI and a native window shell.

> **No Java anywhere.** The Android app layer is written in **Kotlin** (the only
> added dependency is `kotlin-stdlib`); Chaquopy embeds the Python runtime and
> is not a Java dependency. There is no Java source file and no Java library in
> the project. The UI language defaults to **auto** (follow the OS) and the
> Android shell's notification text, channel description and permission toast
> follow the language selected in the Web UI.

## Quick start

```bash
pip install -r requirements.txt
python main.py            # opens the Web UI / native window
python main.py --no-gui --target play.example.net --port 8443
```

Or run a packaged build from `dist/` (build it first with `tools/build.py`).

## Configuration

Configuration lives in `config.json` (created with defaults on first run and
git-ignored — it is machine-local). Common keys:

| Key | Meaning |
|---|---|
| `listen_host` / `wss_port` / `ws_port` | Local endpoint address and ports |
| `target` | Vanilla TCP server to forward to |
| `eagler_translate` | Enable Eaglercraft ↔ vanilla translation |
| `login_ack` | Acknowledge the 1.20.2+ login packet |
| `resource_pack_mode` | `forward` / `prompt` / `ignore` |
| `language` | `auto` (follow the OS, default), `en`, `zh` |
| `startup_notice` | Show the "not mature yet" notice on startup |

## Building

- **Windows**: `tools/build.py` (PyInstaller) → `dist/Server Protocol Bridge.exe`
- **Android**: `android/` Gradle project (Kotlin + Chaquopy) → `app-release.apk`
- **Linux**: `tools/build_wsl.sh` inside WSL2

## Tests

```bash
python -m pytest tests/ -q
```

## Layout

```
proxy/       bridge core: protocol translation, WebSocket/TCP pumps, Web UI, i18n
tools/       build, source export, licence and release helpers
tests/       pytest suite (protocol, translation, crypto, API, Web UI)
web/         release/download website (Cloudflare Pages)
android/     Kotlin Android wrapper (Gradle + Chaquopy)
```

## Licence

See [LICENSE](LICENSE). Third-party notices are in
[THIRD_PARTY_NOTICES.txt](THIRD_PARTY_NOTICES.txt).
