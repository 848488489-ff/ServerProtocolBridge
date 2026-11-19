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
- Every user-visible string must go through `proxy/locales/*.py` (EN and ZH
  tables). Do not hard-code UI text. The interface language defaults to
  Chinese (`config.language = 'zh'`).
- Code comments, identifiers and protocol strings stay English; only
  user-visible text is translated.
- The version number has a single source of truth: `proxy/version_info.py`
  (`VERSION`). `proxy/version.py` imports it, and the matching numbers in
  `android/app/build.gradle` and `web/api/version.json` must be bumped
  together.
- Keep modules small and focused; large files are split by responsibility
  (e.g. `translator_login_*.py`, `proxy_bridge_*.py`).

## Text-file editing (mandatory)

**Never rewrite text files with PowerShell.** `Set-Content`, `Out-File`, `-replace`
piped into a file, and `>` redirection decode and re-encode using the console
code page (GBK/CP936 on this machine). Any UTF-8 file containing `—`, `·`, `→`,
`…`, `©` or CJK text is silently corrupted into U+FFFD replacement characters.
This has already destroyed the website once; do not repeat it.

Rules:

- Edit text files with Python only, always with an explicit encoding:
  `io.open(path, encoding="utf-8").read()` and
  `io.open(path, "w", encoding="utf-8", newline="\n").write(text)`.
- Write plain UTF-8 **without a BOM**. Never use `utf-8-sig` for output; read
  with `utf-8-sig` only when a file is known to carry a BOM.
- Normalise line endings to `\n` (`newline="\n"` on write).
- Prefer the editor/apply-patch tools for small changes; reserve Python scripts
  for bulk rewrites, and print a diff summary afterwards.
- After any bulk edit, audit the result before committing:
  - the file decodes as strict UTF-8,
  - it contains no U+FFFD (`\ufffd`),
  - it has no BOM (`EF BB BF`),
  - non-ASCII punctuation is the intended character, not a mojibake lead (a
    character in the CJK block that appears where ASCII or typographic
    punctuation belongs).
- When a shell command must inspect non-ASCII text, read it through Python and
  print ASCII-safe output. The Windows console mangles Chinese output; console
  mojibake is **not** evidence that the file is broken, and clean console
  output is not evidence that it is fine.

## English-only repository

The repository is English-only. The single exception is in-app UI copy that
ships to end users.

- **Allowed Chinese:** the `zh` entries in `proxy/locales/*.py`, the `zh`
  strings in `web/assets/app.js` / `web/i18n.js`, Chinese content inside
  `web/api/*.json` that is shown on the website, and `README.zh-CN.md`.
- **Everything else is English:** file and directory names, script output and
  log messages, docstrings, code comments, commit messages, documentation,
  release notes in build tooling, and the generated `README.txt` inside the
  source package.
- No Chinese directory names anywhere: the staging directory is
  `source_export/`, never a localized name.
- Any new string that is not user-visible must be written in English, even when
  the surrounding feature is Chinese-facing.

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
  keys), `dist/`, `.wrangler/`, `cloudflare_credentials.json`,
  `local-config-backup/`, or the `source_export/` staging directory.
- **Do commit the release binaries** under `web/downloads/` (EXE, APK, Linux
  ELF and the source ZIP) — the website serves them directly. The ZIP is caught
  by the `*.zip` ignore rule, so add it explicitly with `git add -f`.
- Before committing, run the UTF-8 audit described in "Text-file editing": no
  BOM, no U+FFFD, no mojibake leads, and no Chinese in paths or tooling output.
- Keep each commit focused: one logical change per commit.
