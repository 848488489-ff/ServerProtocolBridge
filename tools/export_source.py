#!/usr/bin/env python3
"""Build a clean source package for Server Protocol Bridge.

Copies the application source into ``源码/procedure`` and the download page
source into ``源码/web``, writes a manifest, then creates a versioned ZIP next
to this project.  Finally it records the ZIP size in the website's
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
# ``superdebug`` is the Minecraft debug plugin: its source, build script and
# the built SuperDebug-1.1.0.jar ship in the source package (the JAR is a
# release artifact, not a binary of this program, so ARCHIVE_SKIP_SUFFIXES
# deliberately does not contain .jar).
APP_DIRS = ("proxy", "tests", "tools", "android", "superdebug")
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
    ".gradle",
    ".idea",
    "captures",
}
APP_SKIP_FILES = {
    "config.json",
    "config.example.json",
    ".DS_Store",
    "Thumbs.db",
    "local.properties",
}
APP_SKIP_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".pyd",
    ".exe",
    ".log",
    ".zip",
    ".iml",
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


# Files that must never be folded into the archive: they are themselves
# archives or release binaries, and nesting one of these inside its own source
# package is how the export starts shipping downloads/ forever.
ARCHIVE_SKIP_SUFFIXES = {
    ".7z",
    ".zip",
    ".rar",
    ".tar",
    ".gz",
    ".tgz",
    ".bz2",
    ".xz",
    ".exe",
    ".msi",
}


def build_zip(source_root: Path, zip_path: Path) -> None:
    if zip_path.exists():
        zip_path.unlink()
    skipped: list[str] = []
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(source_root.rglob("*")):
            if not path.is_file():
                continue
            name = path.name.lower()
            if name.endswith(tuple(ARCHIVE_SKIP_SUFFIXES)) or "downloads" in name:
                skipped.append(path.name)
                continue
            archive.write(path, path.relative_to(source_root).as_posix())
    for name in sorted(set(skipped)):
        log(f"      excluded {name} (archive or binary, kept out of the package)")


def sanitize_packaged_version(web_root_dest: Path) -> None:
    """Remove self-referential archive metadata from the packaged web copy.

    The ZIP cannot contain its own final size, and the live
    api/version.json is updated from the finished archive after compression.
    Keeping stale numbers inside the package would make the bundled site lie.
    """
    version_json = web_root_dest / "api" / "version.json"
    if not version_json.exists():
        return
    data = json.loads(version_json.read_text(encoding="utf-8-sig"))
    for key in ("source_size", "source_updated"):
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
        data["source_name"] = zip_path.name
        data["source_version"] = version
        data["source_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    data.setdefault("source_url", "")
    version_json.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _join_url(base: str, relative: str) -> str:
    """Combine the site origin with a manifest path.

    ``download_url`` and ``source_url`` are usually paths relative to the site
    root, but either field may already be an absolute link, so only prefix when
    it actually needs one.
    """
    origin = (base or "").strip().rstrip("/")
    path = (relative or "").strip()
    if not origin:
        return path
    if path.startswith(("http://", "https://")):
        return path
    return origin + (path if path.startswith("/") else "/" + path)


def build_readme(version: str, generated_at: str, version_json: Path) -> str:
    """Package README, Chinese first then English.

    The archive deliberately holds no binaries and no ``downloads`` directory --
    that folder is served by the release site, and shipping it inside its own
    source archive would nest the package forever.  The README points to the
    site instead.
    """
    data: dict = {}
    if version_json.is_file():
        data = json.loads(version_json.read_text(encoding="utf-8-sig"))
    page = str(data.get("page_url") or "").strip()
    exe_url = _join_url(page, str(data.get("download_url") or ""))
    linux_url = _join_url(page, str(data.get("linux_url") or ""))
    linux_line = (
        "\n      Linux 程序 (x86_64, glibc 2.36+)\n       {0}\n".format(linux_url)
        if linux_url else ""
    )
    linux_line_en = (
        "\n   Linux program (x86_64, glibc 2.36+)\n     {0}\n".format(linux_url)
        if linux_url else ""
    )
    # Derive the archive name from the version instead of reading
    # ``source_name`` / ``source_url`` off the manifest: export_source only
    # rewrites the size and hash fields, so those two still point at the
    # previous release until the archive is uploaded.
    zip_name = "ServerProtocolBridge-{v}-source.zip".format(v=version)
    zip_url = _join_url(page, "/downloads/" + zip_name)

    return f"""Server Protocol Bridge {version} - 源码包 / source package
生成时间 / Generated: {generated_at}

================================================================
一、中文说明
================================================================

1. 怎么获取发布的程序

   本源码包不包含任何可执行文件, 也不包含网站的 downloads 目录。
   发布文件(Windows 程序、源码压缩包)托管在发布站点上, 按下面的地址下载:

     发布页面
       {page}

     Windows 程序
       {exe_url}
{linux_line}
     源码压缩包 {zip_name}
       {zip_url}

   发布站点的 api/version.json 是权威清单:
     version        版本号
     file_size      程序的字节数
     source_size    源码压缩包的字节数


2. 目录结构

   procedure/    Python 应用源码。
   web/          静态发布/下载页面的源码。
   LICENSE       许可证全文(Unlicense, 公有领域)。
   README.txt    本说明。
   SOURCE-MANIFEST.json  每个文件的 SHA-256。


3. 运行 procedure

   准备 Python 3.10 或更高版本, 然后:
       py -3 -m pip install -r requirements.txt
       py -3 main.py

   Linux / macOS 用 python3 代替 py, 或直接运行:
       sh start.sh

   PyInstaller 不支持交叉编译, 每个平台只生成自己的二进制:

   Linux / macOS 打包(可选):
       sh tools/build.sh

   Windows 打包(可选):
       py -3 -m pip install -r requirements-build.txt
       py -3 tools/build.py

   Windows + WSL2 想构建 Linux 版本时, 在仓库根目录运行:
       powershell -ExecutionPolicy Bypass -File tools\build_wsl.ps1
   (首次运行会在 WSL 内自动创建虚拟环境并安装依赖; 结果为
   dist/Server Protocol Bridge, 是 Linux ELF 可执行文件)

   Android 原生 APK(需要 Android Studio):
      android/ 目录是 Android Studio Gradle 项目, 用 Chaquopy 嵌入
      Python, 控制面板由内置 WebView 显示。打开 android/ 后构建
      APK; 详见 android/README.md。

   第三方组件及其完整许可证文本见 THIRD_PARTY_NOTICES.txt,
   可用下面的命令重新生成:
       py -3 tools/collect_licenses.py


4. 运行 web

   web/index.html 是静态发布页面, 可以直接用浏览器打开, 也可以用任意
   静态文件服务器托管整个目录。发布数据来自 api/version.json, 常见问题
   来自 api/faq.json, 接口文档是 api/index.html。

   包内 api/version.json 故意省略了 source_size 与
   source_updated: 压缩包无法包含自己的最终哈希。这两个字段以线上站点
   的 api/version.json 为准。


5. 本包故意不包含的内容

   - build/、dist/、*.exe 等发布产物
   - web 的 downloads/ 目录(发布站点才有的部署内容, 放进自己的源码包
     会无限套娃)
   - certs/(本地 TLS 私钥)
   - config.json、日志、缓存、__pycache__
   - 独立的 admin.html 测试页面

   要重新导出源码包, 在仓库根目录运行:
       py -3 tools/export_source.py


================================================================
二、English
================================================================

1. Where to get the released program

   This archive contains no binaries and no downloads directory.  The
   release files are hosted by the release site:

     Release page
       {page}

     Windows program
       {exe_url}
{linux_line_en}
     Source archive {zip_name}
       {zip_url}

   The site's api/version.json is the authoritative manifest:
     version        release number
     file_size      size of the program in bytes
     source_size    size of this archive in bytes


2. Layout

   procedure/    Python application source.
   web/          Source of the static release page.
   LICENSE       Licence text (Unlicense, public-domain dedication).
   README.txt    This file.
   SOURCE-MANIFEST.json  SHA-256 of every file.


3. Running procedure

   Python 3.10 or newer, then:
       py -3 -m pip install -r requirements.txt
       py -3 main.py

   On Linux / macOS use python3 instead of py, or run:
       sh start.sh

   PyInstaller cannot cross-compile, so each platform builds its own binary:

   Linux / macOS (optional):
       sh tools/build.sh

   Windows (optional):
       py -3 -m pip install -r requirements-build.txt
       py -3 tools/build.py

   On Windows with WSL2, build the Linux binary from the repository root:
       powershell -ExecutionPolicy Bypass -File tools\build_wsl.ps1
   (the first run creates a virtual environment inside WSL and installs the
   dependencies; the result is dist/Server Protocol Bridge, a Linux ELF)

   Android native APK (requires Android Studio):
      android/ is an Android Studio Gradle project that embeds Python via
      Chaquopy; the control panel is shown in a built-in WebView.  Open
      android/ and build the APK; see android/README.md.

   Third-party components and their full licence texts are in
   THIRD_PARTY_NOTICES.txt.  Regenerate that file with:
       py -3 tools/collect_licenses.py


4. Running web

   web/index.html is the static release page.  Open it directly in a browser,
   or serve the folder with any static file server.  Release data comes from
   api/version.json, FAQ content from api/faq.json, and the API reference is
   api/index.html.

   The packaged api/version.json omits source_size and
   source_updated on purpose: an archive cannot contain its own final hash.
   The live site's api/version.json is authoritative for those fields.


5. Deliberately not included

   - build/, dist/, *.exe and other release binaries
   - web's downloads/ directory (deployment content that only the release
     site has; shipping it inside its own source archive would nest the
     package forever)
   - certs/ (local TLS private keys)
   - config.json, logs, caches and __pycache__
   - the standalone admin.html test page

   To export the source package again, run from the repository root:
       py -3 tools/export_source.py


See SOURCE-MANIFEST.json for every file and its SHA-256.
"""


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

    readme = build_readme(version, generated_at, web_root / "api" / "version.json")
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
        log("[4/4] updated api/version.json with source_size")
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
