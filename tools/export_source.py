#!/usr/bin/env python3
"""Build a clean source package for Server Protocol Bridge.

Copies the application source into ``源码/procedure`` and the download page
source into ``源码/web``, writes a manifest, then creates a versioned ZIP next
to this project.  Finally it records the ZIP size and SHA-256 in the website's
``api/version.json`` so the "Get source" button can show trustworthy metadata.

Usage (from anywhere):

    py tools/export_source.py

Optional:

    py tools/export_source.py --web-root "D:\\path\\to\\version-check"
    py tools/export_source.py --no-zip

The netdisk URL cannot be generated locally, so ``source_url`` is preserved
from api/version.json.  Upload the ZIP and paste its direct link there.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
DEST_ROOT = APP_ROOT / "源码"
DEFAULT_WEB_ROOT = Path(r"D:\桌面\版本更新检查")

APP_FILES = (
    ".gitignore",
    "LICENSE",
    "main.py",
    "requirements.txt",
    "requirements-build.txt",
    "THIRD_PARTY_NOTICES.txt",
    "start.bat",
    "start.sh",
)
APP_DIRS = ("proxy", "tests", "tools")
APP_SKIP_DIRS = {
    "__pycache__",
    ".pytest_cache",
    ".git",
    ".venv",
    "venv",
    "build",
    "dist",
    "certs",
    "源码",
}
APP_SKIP_FILES = {
    "config.json",
    "config.example.json",
    ".DS_Store",
    "Thumbs.db",
}
APP_SKIP_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".pyd",
    ".exe",
    ".log",
    ".zip",
}

WEB_FILES = (
    "LICENSE",
    "index.html",
    "i18n.js",
    "icon.svg",
    "favicon.ico",
    "_headers",
)
# Copy the whole API directory, not just version/FAQ: the static reference and
# every JSON endpoint are part of the website source package.
WEB_DIRS = ("assets", "api")
# The live site may host the release binary under /downloads so it can be linked
# from the manifest without a third-party CDN.  That directory is deployment
# content, not source, so it is deliberately kept out of the source package.
WEB_SKIP_DIRS = {"node_modules", ".git", "__pycache__", "downloads"}
WEB_SKIP_FILES = {"admin.html", ".DS_Store", "Thumbs.db"}
WEB_SKIP_SUFFIXES = {".log", ".zip", ".exe"}


def log(message: str) -> None:
    print(message, flush=True)


def should_skip(path: Path, skip_dirs: set[str], skip_files: set[str], skip_suffixes: set[str]) -> bool:
    if path.is_dir():
        return path.name in skip_dirs
    return path.name in skip_files or path.suffix.lower() in skip_suffixes


def copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def copy_tree(
    source: Path,
    destination: Path,
    skip_dirs: set[str],
    skip_files: set[str],
    skip_suffixes: set[str],
) -> list[Path]:
    copied: list[Path] = []
    if not source.exists():
        return copied
    for item in sorted(source.iterdir(), key=lambda value: value.name.lower()):
        if should_skip(item, skip_dirs, skip_files, skip_suffixes):
            continue
        target = destination / item.name
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            copied.extend(copy_tree(item, target, skip_dirs, skip_files, skip_suffixes))
        elif item.is_file():
            copy_file(item, target)
            copied.append(target)
    return copied


def reset_directory(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def wire_manifest(files: list[Path], root: Path) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for path in sorted(files):
        relative = path.relative_to(root).as_posix()
        entries.append(
            {
                "path": relative,
                "bytes": path.stat().st_size,
                "sha256": sha256_of(path),
            }
        )
    return entries


def build_zip(source_root: Path, zip_path: Path) -> None:
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(source_root.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(source_root).as_posix())


def sanitize_packaged_version(web_root_dest: Path) -> None:
    """Remove self-referential archive metadata from the packaged web copy.

    The ZIP cannot contain its own final size or SHA-256, and the live
    api/version.json is updated from the finished archive after compression.
    Keeping stale numbers inside the package would make the bundled site lie.
    """
    version_json = web_root_dest / "api" / "version.json"
    if not version_json.exists():
        return
    data = json.loads(version_json.read_text(encoding="utf-8-sig"))
    for key in ("source_size", "source_sha256", "source_updated"):
        data.pop(key, None)
    version_json.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def update_version_json(version_json: Path, zip_path: Path | None, version: str) -> None:
    if not version_json.exists():
        return
    data = json.loads(version_json.read_text(encoding="utf-8-sig"))
    if zip_path and zip_path.exists():
        data["source_size"] = zip_path.stat().st_size
        data["source_sha256"] = sha256_of(zip_path)
        data["source_name"] = zip_path.name
        data["source_version"] = version
        data["source_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    data.setdefault("source_url", "")
    version_json.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Export the Server Protocol Bridge source package.")
    parser.add_argument("--web-root", type=Path, default=DEFAULT_WEB_ROOT, help="Path to the version-check website.")
    parser.add_argument("--no-zip", action="store_true", help="Copy the tree but skip creating the ZIP.")
    args = parser.parse_args()

    web_root = args.web_root.expanduser().resolve()
    if not (web_root / "index.html").exists():
        log(f"[error] website not found: {web_root}")
        return 1

    version_file = APP_ROOT / "proxy" / "version.py"
    version = "0.0.0"
    for line in version_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("VERSION ="):
            version = line.split("=", 1)[1].strip().strip("'\"")
            break

    procedure_root = DEST_ROOT / "procedure"
    web_root_dest = DEST_ROOT / "web"
    reset_directory(procedure_root)
    reset_directory(web_root_dest)
    copy_file(APP_ROOT / "LICENSE", DEST_ROOT / "LICENSE")

    log(f"[1/4] exporting application source -> {procedure_root}")
    copied_app: list[Path] = []
    for name in APP_FILES:
        source = APP_ROOT / name
        if source.is_file():
            target = procedure_root / name
            copy_file(source, target)
            copied_app.append(target)
    for name in APP_DIRS:
        copied_app.extend(
            copy_tree(
                APP_ROOT / name,
                procedure_root / name,
                APP_SKIP_DIRS,
                APP_SKIP_FILES,
                APP_SKIP_SUFFIXES,
            )
        )

    log(f"[2/4] exporting website source -> {web_root_dest}")
    copied_web: list[Path] = []
    for name in WEB_FILES:
        source = web_root / name
        if source.is_file():
            target = web_root_dest / name
            copy_file(source, target)
            copied_web.append(target)
    for name in WEB_DIRS:
        copied_web.extend(
            copy_tree(
                web_root / name,
                web_root_dest / name,
                WEB_SKIP_DIRS,
                WEB_SKIP_FILES,
                WEB_SKIP_SUFFIXES,
            )
        )

    sanitize_packaged_version(web_root_dest)

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    manifest = {
        "name": "Server Protocol Bridge",
        "version": version,
        "generated_at": generated_at,
        "application": wire_manifest(copied_app, procedure_root),
        "website": wire_manifest(copied_web, web_root_dest),
        "package": wire_manifest([DEST_ROOT / "LICENSE"], DEST_ROOT),
    }
    (DEST_ROOT / "SOURCE-MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    readme = f"""Server Protocol Bridge {version} - source package
Generated: {generated_at}

procedure/
  Python application source. Run it with:
      py -3 -m pip install -r requirements.txt
      py -3 main.py

  Linux/macOS: use python3 instead of py, or run:
      sh start.sh
  PyInstaller cannot cross-compile, so the source package is the supported
  way to run the app on those platforms.

  Windows EXE build (optional; Windows only):
      py -3 -m pip install -r requirements-build.txt
      py -3 tools/build.py

  Third-party components and their full license texts are listed in
  THIRD_PARTY_NOTICES.txt.  Regenerate that file with:
      py -3 tools/collect_licenses.py

License
  This project is released under the Unlicense (public-domain dedication).
  The full text is in LICENSE at the package root and in procedure/LICENSE.
  See https://unlicense.org/ for the canonical text.

web/
  The static release/download page. Open index.html directly, or serve the
  folder with any static file server. Release data comes from api/version.json
  and FAQ content comes from api/faq.json. The API reference is api/index.html.

  The packaged api/version.json omits source_size, source_sha256 and
  source_updated on purpose: an archive cannot contain its own final hash.
  The live site's api/version.json is authoritative for those fields.

The following are intentionally not part of this package:
  - build/, dist/, *.exe and other release binaries
  - certs/ (local TLS private keys)
  - config.json, logs, caches and __pycache__ directories
  - the standalone admin.html prank page

See SOURCE-MANIFEST.json for every file and its SHA-256.
"""
    (DEST_ROOT / "README.txt").write_text(readme, encoding="utf-8")

    log(f"      application files: {len(copied_app)}")
    log(f"      website files:     {len(copied_web)}")

    zip_path = APP_ROOT / f"ServerProtocolBridge-{version}-source.zip"
    if not args.no_zip:
        log(f"[3/4] building archive -> {zip_path.name}")
        build_zip(DEST_ROOT, zip_path)
        update_version_json(web_root / "api" / "version.json", zip_path, version)
        size_mb = zip_path.stat().st_size / (1024 * 1024)
        log(f"      size:   {size_mb:.2f} MB ({zip_path.stat().st_size} bytes)")
        log(f"      sha256: {sha256_of(zip_path)}")
        log("[4/4] updated api/version.json with source_size and source_sha256")
        log("      upload the ZIP to your netdisk, then put the direct link in api/version.json -> source_url")
    else:
        log("[3/4] skipped ZIP (--no-zip)")
        log("[4/4] api/version.json was not updated")

    log("")
    log(f"done: {DEST_ROOT}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        log("cancelled")
        raise SystemExit(130)
