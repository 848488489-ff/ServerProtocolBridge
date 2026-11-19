# Server Protocol Bridge

> **This build is not mature yet; it is not recommended on servers with strict anti-cheat.**

`Server Protocol Bridge` turns a plain vanilla Minecraft **Java Edition** TCP
server into a local `wss://` / `ws://` endpoint, so a browser-based
**Eaglercraft** client (which cannot speak the native TCP protocol) can join it.
The JVM is not involved on the client side at all.

## What it does

- Listens on a local `wss://` (TLS, self-signed CA) / `ws://` endpoint.
- Speaks the **Eaglercraft handshake dialects v1–v5** to the browser client
  (negotiated per connection, including v5 capability bits and extensions).
- Translates between the Eaglercraft wire format and the **vanilla Minecraft
  protocol** (VarInt framing, compression threshold, login/play phases).
- Answers the server's **encryption request on the client's behalf**: a random
  shared secret is RSA-encrypted with the server's public key, the session is
  registered with the Mojang join service when an authenticated account is
  selected, and both directions switch to AES-128-CFB8.
- Answers the browser client's **server-list MOTD** query locally.
- Resolves the target via **SRV records**, keeps a **status cache**, and
  forwards resource packs (configurable).
- Cross-platform: Windows EXE, Android APK (Chaquopy), Linux (AppImage/deb/rpm),
  plus a Web UI and a native GUI shell.

## Quick start

```bash
pip install -r requirements.txt
python main.py            # opens the Web UI / native window
python main.py --no-gui --target play.example.net --port 8443
```

Or run the packaged binary from `dist/` (after `tools/build.py`).

## Configuration

Configuration lives in `config.json` (created with defaults on first run, and
ignored by git — it is machine-local). Notable keys:

| Key | Meaning |
|---|---|
| `listen_host` / `wss_port` / `ws_port` | Local endpoint address and ports |
| `target` | The vanilla TCP server to relay to |
| `eagler_translate` | Enable Eaglercraft ↔ vanilla translation |
| `login_ack` | Answer the 1.20.2+ login-acknowledged packet |
| `resource_pack_mode` | `forward` / `prompt` / `ignore` |
| `language` | `auto` (detect system), `en`, `zh` |
| `startup_notice` | Show the "not mature yet" notice on start |

## Building

- **Windows**: `tools/build.py` (PyInstaller) → `dist/Server Protocol Bridge.exe`
- **Android**: `android/` Gradle project (Chaquopy) → `app-release.apk`
- **Linux**: `tools/build_wsl.sh` inside WSL2

## Testing

```bash
python -m pytest tests/ -q
```

## Layout

```
proxy/       The bridge: protocol translation, WebSocket/TCP pump, Web UI, i18n
tools/       Build, export-source, license and release helpers
tests/       Pytest suite (protocol, translation, crypto, API, Web UI)
web/         The project update/download website (Cloudflare Pages)
android/     Chaquopy Android wrapper (Gradle)
```

## License

See [LICENSE](LICENSE). Third-party notices are in
[THIRD_PARTY_NOTICES.txt](THIRD_PARTY_NOTICES.txt).
