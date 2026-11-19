#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deploy the website directory (``web/``) to Cloudflare Pages using the
Direct Upload API.

Credentials are read from environment variables ONLY (never hard-coded):
    CLOUDFLARE_API_TOKEN      (API token / KEY)
    CLOUDFLARE_ACCOUNT_ID     (Cloudflare account id)
    CLOUDFLARE_PAGES_PROJECT  (Cloudflare Pages project name, e.g. noppnb666)

Usage:
    set CLOUDFLARE_API_TOKEN=...      (or $env: in PowerShell)
    set CLOUDFLARE_ACCOUNT_ID=...
    set CLOUDFLARE_PAGES_PROJECT=noppnb666
    python deploy.py

This deploys the whole site directory, including the /downloads binaries.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# The website directory lives next to this script (repository layout).
SITE = Path(__file__).resolve().parent / "web"
BRANCH = "main"
TIMEOUT = 600


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        print(f"[deploy] Missing environment variable {name}. Set it and run again.",
              file=sys.stderr)
        sys.exit(2)
    return value


TOKEN = require_env("CLOUDFLARE_API_TOKEN")
ACCOUNT = require_env("CLOUDFLARE_ACCOUNT_ID")
PROJECT = require_env("CLOUDFLARE_PAGES_PROJECT")

API = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}/pages/projects/{PROJECT}"


def request(method: str, url: str, payload: dict | None = None, raw: bytes | None = None,
            content_type: str = "application/json", timeout: int = TIMEOUT) -> dict:
    headers = {"Authorization": f"Bearer {TOKEN}"}
    data = None
    if raw is not None:
        data = raw
        headers["Content-Type"] = content_type
    elif payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = content_type
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
    try:
        return json.loads(body.decode("utf-8"))
    except Exception:
        return {"success": False, "raw": body[:300].decode("utf-8", "replace")}


def api_ok(resp: dict, what: str) -> dict:
    if not resp.get("success"):
        errors = resp.get("errors") or resp.get("raw") or resp
        print(f"[deploy] {what} failed: {json.dumps(errors, ensure_ascii=False)}",
              file=sys.stderr)
        sys.exit(1)
    return resp["result"]


def collect_files() -> list[tuple[str, Path]]:
    files: list[tuple[str, Path]] = []
    for path in sorted(SITE.rglob("*")):
        if path.is_file():
            files.append((path.relative_to(SITE).as_posix(), path))
    return files


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    if not SITE.is_dir():
        print(f"[deploy] Website directory not found: {SITE}", file=sys.stderr)
        return 1

    files = collect_files()
    if not files:
        print("[deploy] Website directory is empty", file=sys.stderr)
        return 1

    total_bytes = sum(p.stat().st_size for _, p in files)
    print(f"[deploy] Site: {SITE}")
    print(f"[deploy] Files: {len(files)}   total size: {total_bytes / 1024 / 1024:.2f} MB")
    print(f"[deploy] Project: {PROJECT}  @ branch {BRANCH}")

    # 1) Create the deployment (Direct Upload carries the file hash manifest).
    hashes = [{"path": "/" + rel, "sha256": sha256_of(p)} for rel, p in files]
    created = api_ok(
        request("POST", f"{API}/deployments",
                {"branch": BRANCH, "file_hashes": hashes}),
        "Create deployment",
    )
    deployment_id = created["id"]
    upload_url = created["url"]
    print(f"[deploy] Deployment {deployment_id} created; uploading {len(files)} files...")

    # 2) Upload each file to {upload_url}/{sha256} in parallel.
    done = 0

    def upload_one(item: tuple[str, Path]) -> str:
        rel, path = item
        digest = sha256_of(path)
        with path.open("rb") as handle:
            data = handle.read()
        resp = request("PUT", f"{upload_url}/{digest}", raw=data,
                       content_type="application/octet-stream")
        if not resp.get("success"):
            raise RuntimeError(f"Upload failed {rel}: {resp}")
        return rel

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(upload_one, item): item for item in files}
        for future in concurrent.futures.as_completed(futures):
            rel = futures[future][0]
            try:
                future.result()
                done += 1
                if done % 25 == 0 or done == len(files):
                    print(f"[deploy] Uploaded {done}/{len(files)}")
            except Exception as exc:
                print(f"[deploy] File upload error {rel}: {exc}", file=sys.stderr)
                return 1

    # 3) Poll the deployment until it finishes.
    print("[deploy] All files uploaded; waiting for the deployment to finish...")
    for _ in range(60):
        time.sleep(5)
        status = api_ok(
            request("GET", f"{API}/deployments/{deployment_id}"), "Query status")
        stage = (status.get("latest_stage") or {}).get("status", "?")
        if stage in ("success", "failed", "error"):
            if stage == "success":
                url = status.get("url", "?")
                print(f"[deploy] Deployment succeeded: {url}")
                return 0
            print(f"[deploy] Deployment status: {stage}", file=sys.stderr)
            return 1
        print(f"[deploy]   Deploying... stage={stage}")

    print("[deploy] Timeout; the deployment did not finish. Check the Cloudflare "
          "dashboard.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
