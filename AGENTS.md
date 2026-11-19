# AGENTS.md — Project guidance for AI coding agents

This file describes how to work in this repository correctly. All text in this
file is intentionally English, and commit messages must also be English.

## Project overview

`Server Protocol Bridge` is a Python relay that connects an Eaglercraft
(browser / WebAssembly) Minecraft Java Edition client to a plain vanilla
Minecraft TCP server. It listens on a local `wss://` / `ws://` endpoint and
translates between the Eaglercraft wire format (handshake dialects v1–v5) and
the vanilla Minecraft protocol (VarInt framing, compression, login/play
phases).

There is no JVM on the client side; the relay is pure Python plus optional
native TLS/crypto backends.

## Environment

- Python 3.12+ is required to run the source.
- Third-party deps are in `requirements.txt` (`websockets`, `cryptography`,
  `pywebview`, ...). Install with `pip install -r requirements.txt`.
- Tests need `pytest`.

## Commands

```bash
# run the bridge (Web UI / native window)
python main.py

# run headless against a target
python main.py --no-gui --target play.example.net --port 8443

# run the full test suite
python -m pytest tests/ -q

# build the Windows EXE (PyInstaller)
python tools/build.py
```

## Testing rules

- Never merge a change that breaks `python -m pytest tests/ -q`.
- The protocol and translation tests are the ones most likely to be touched by
  a change to the relay; run `tests/test_translate.py` and `tests/test_all.py`
  before committing.
- Keep tests deterministic: do not rely on the operator's local `config.json`,
  network state, or absolute paths.

## Code style

- Follow the surrounding style: type hints (`from __future__ import
  annotations`), dataclasses for state, i18n via `proxy/i18n.py` (`tr()`).
- Every user-visible string must go through `proxy/locales/*.py` (the EN table;
  the project is English-only, there is no second language table).
  Do not hard-code UI text.
- Keep modules small and focused; large files are split by responsibility
  (e.g. `translator_login_*.py`, `proxy_bridge_*.py`).

## Architecture notes

- `proxy/vanilla.py` — vanilla Minecraft framing (Decoder/Encoder, VarInt,
  compression). It is deliberately version-tolerant for the ids it must know;
  packet-id maps live there.
- `proxy/eagler.py` — the Eaglercraft handshake dialects (v1–v5), negotiated
  per connection (`select_protocols`).
- `proxy/translator_*.py` — the translation layer: login (incl. encryption
  answered on the client's behalf), play, chat, resource packs, spoof.
- `proxy/proxy_bridge_pump.py` — the asyncio pumps that move bytes between the
  browser WebSocket and the backend TCP socket. `CLOSE_GRACE` (proxy.py) is the
  graceful-shutdown window that gives the browser time to render a disconnect
  reason before the WebSocket is dropped.
- The relay forwards game packets verbatim and does NOT do cross-version
  packet-id translation; version handling is left to the target server.

## Git rules

- **Commit messages must be in English**, in the conventional style already
  used by this repository: `fix:`, `feat:`, `chore:`, `docs:`, `build:`,
  `ci:`, `test:` followed by a lowercase summary.
- Do not commit machine-local artifacts: `config.json`, `certs/` (private
  keys), `dist/`, `web/downloads/` (release binaries), `.wrangler/`,
  `cloudflare_credentials.json`, or `local-config-backup/`.
- Keep each commit focused: one logical change per commit.
