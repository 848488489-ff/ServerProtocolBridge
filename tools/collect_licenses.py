#!/usr/bin/env python3
"""Regenerate THIRD_PARTY_NOTICES.txt from the current build environment.

The notices file belongs to the source package.  The Windows EXE does not
embed it: the About window shows the compact component/license/project list
from proxy/third_party.py, and links to each project.

Usage (from anywhere):

    py tools/collect_licenses.py
"""

from __future__ import annotations

import hashlib
import importlib.metadata as metadata
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from proxy.third_party import COMPONENTS, STDLIB_MODULES  # noqa: E402

OUTPUT = ROOT / "THIRD_PARTY_NOTICES.txt"

DIST_NAMES = {
    "websockets": "websockets",
    "cryptography": "cryptography",
    "cffi": "cffi",
    "pycparser": "pycparser",
    "mcauth3": "mcauth3",
    "requests": "requests",
    "urllib3": "urllib3",
    "charset-normalizer": "charset-normalizer",
    "certifi": "certifi",
    "idna": "idna",
    "pywebview": "pywebview",
    "pythonnet (.NET bridge)": "pythonnet",
    "clr_loader": "clr_loader",
    "Flask": "flask",
    "Werkzeug": "werkzeug",
    "Jinja2": "jinja2",
    "click": "click",
    "itsdangerous": "itsdangerous",
    "blinker": "blinker",
    "MarkupSafe": "markupsafe",
    "PyInstaller": "pyinstaller",
}

EXTRA_PACKAGES = (
    ("pycryptodome", "Optional AES fallback (not included in the official build)"),
    ("pillow", "Build-only icon generator"),
)

OPENSSL_NOTE = (
    "OpenSSL 3.x ships with the program as the libssl/libcrypto DLLs that the "
    "Python ssl module loads. OpenSSL is licensed under the Apache License 2.0; "
    "its copyright notice is retained by the OpenSSL project. "
    "Project: https://www.openssl.org/"
)


def license_files(distribution: metadata.Distribution) -> list[Path]:
    found: list[Path] = []
    for item in distribution.files or []:
        name = str(item).lower()
        if not any(part in name for part in ("license", "copying", "notice")):
            continue
        if name.endswith((".py", ".pyc")):
            continue
        path = distribution.locate_file(item)
        if path.is_file():
            found.append(Path(path))
    return found


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace").strip()


def main() -> int:
    entries: list[dict[str, object]] = []
    texts: dict[str, dict[str, object]] = {}

    def add_text(text: str, label: str, package: str) -> str:
        normalized = text.strip()
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        if digest not in texts:
            texts[digest] = {
                "label": f"L{len(texts) + 1}",
                "title": label,
                "text": normalized,
                "packages": [],
            }
        packages = texts[digest]["packages"]
        assert isinstance(packages, list)
        if package not in packages:
            packages.append(package)
        return str(texts[digest]["label"])

    for component in COMPONENTS:
        name = str(component["name"])
        if name == "Python":
            python_license = Path(sys.base_prefix) / "LICENSE.txt"
            refs: list[str] = []
            if python_license.is_file():
                refs.append(add_text(read_text(python_license), "Python PSF-2.0", name))
            entries.append({
                "name": name,
                "version": platform.python_version(),
                "license": str(component["license"]),
                "url": str(component["url"]),
                "role": "Runtime",
                "refs": refs,
            })
            continue

        if name == "CPython interpreter":
            python_license = Path(sys.base_prefix) / "LICENSE.txt"
            refs = []
            if python_license.is_file():
                refs.append(add_text(read_text(python_license), "Python PSF-2.0", name))
            entries.append({
                "name": name,
                "version": platform.python_version(),
                "license": str(component["license"]),
                "url": str(component["url"]),
                "role": "Runtime",
                "refs": refs,
            })
            continue

        if name == "OpenSSL (bundled)":
            entries.append({
                "name": name,
                "version": "3.x (libssl/libcrypto DLLs)",
                "license": str(component["license"]),
                "url": str(component["url"]),
                "role": "Runtime",
                "refs": [],
            })
            continue

        dist_name = DIST_NAMES.get(name)
        if not dist_name:
            continue
        try:
            dist = metadata.distribution(dist_name)
        except metadata.PackageNotFoundError:
            print(f"[warning] package not installed: {dist_name}", file=sys.stderr)
            entries.append({
                "name": name,
                "version": "not installed",
                "license": str(component["license"]),
                "url": str(component["url"]),
                "role": "Runtime",
                "refs": [],
            })
            continue

        refs = []
        for path in license_files(dist):
            refs.append(add_text(
                read_text(path),
                f"{dist.metadata['Name']} {dist.version} - {path.name}",
                name,
            ))

        entries.append({
            "name": name,
            "version": dist.version,
            "license": str(component["license"]),
            "url": str(component["url"]),
            "role": "Build tool / bootloader" if name == "PyInstaller" else "Runtime",
            "refs": refs,
        })

    for dist_name, role in EXTRA_PACKAGES:
        try:
            dist = metadata.distribution(dist_name)
        except metadata.PackageNotFoundError:
            print(f"[warning] optional package not installed: {dist_name}", file=sys.stderr)
            continue
        refs = [
            add_text(read_text(path), f"{dist.metadata['Name']} {dist.version} - {path.name}",
                     dist.metadata["Name"])
            for path in license_files(dist)
        ]
        entries.append({
            "name": dist.metadata["Name"],
            "version": dist.version,
            "license": dist.metadata.get("License-Expression")
            or dist.metadata.get("License")
            or "see license text",
            "url": "https://pypi.org/project/%s/" % dist.metadata["Name"],
            "role": role,
            "refs": refs,
        })

    lines: list[str] = []
    lines.append("Server Protocol Bridge - third-party notices")
    lines.append("=" * 78)
    lines.append("")
    lines.append("Generated: %s" % datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"))
    lines.append("Python:   %s" % platform.python_version())
    lines.append("")
    lines.append("This file is part of the source distribution.  The Windows EXE does not")
    lines.append("embed it: the About window lists each component, its license and a project")
    lines.append("link; the complete license texts are collected here for the source package.")
    lines.append("")
    lines.append("Project license: Unlicense (public-domain dedication).")
    lines.append("The full text is in LICENSE at the package root and in procedure/LICENSE;")
    lines.append("see https://unlicense.org/ for the canonical text.")
    lines.append("")
    lines.append("Component inventory")
    lines.append("-" * 78)
    for entry in entries:
        refs = entry["refs"]
        ref_text = ", ".join(refs) if refs else "no license file found"
        lines.append("%-22s %-12s %-34s %s" % (
            entry["name"], entry["version"], entry["license"], entry["role"]))
        lines.append("    %s  [%s]" % (entry["url"], ref_text))
    lines.append("")
    lines.append("Python standard library modules (PSF-2.0)")
    lines.append("-" * 78)
    for module in STDLIB_MODULES:
        lines.append("%-24s https://docs.python.org/3/library/%s.html" % (module, module))
    lines.append("")
    lines.append("Each module above is part of CPython and is covered by the PSF-2.0")
    lines.append("license. It is listed separately because minimal or embedded Python")
    lines.append("distributions may omit standard library modules such as random, ssl,")
    lines.append("secrets or asyncio.")
    lines.append("")
    lines.append("Notes")
    lines.append("-" * 78)
    lines.append(OPENSSL_NOTE)
    lines.append("")
    lines.append("certifi is distributed unmodified under MPL-2.0. Its source is available at")
    lines.append("https://github.com/certifi/python-certifi.")
    lines.append("")
    lines.append("License texts")
    lines.append("=" * 78)
    for item in texts.values():
        lines.append("")
        lines.append("[%s] %s" % (item["label"], item["title"]))
        lines.append("Used by: %s" % ", ".join(item["packages"]))
        lines.append("-" * 78)
        lines.append(str(item["text"]))
        lines.append("")

    OUTPUT.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print("wrote %s (%d bytes, %d packages, %d unique license texts)" % (
        OUTPUT, OUTPUT.stat().st_size, len(entries), len(texts)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
