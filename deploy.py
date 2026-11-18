#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deploy the website directory (D:\\桌面\\版本更新检查) to Cloudflare Pages
using the Direct Upload API.

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

SITE = Path(r"D:\桌面\版本更新检查")
BRANCH = "main"
TIMEOUT = 600


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        print(f"[deploy] 缺少环境变量 {name} —— 请在环境变量里设置后再运行。", file=sys.stderr)
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
        print(f"[deploy] {what} 失败: {json.dumps(errors, ensure_ascii=False)}", file=sys.stderr)
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
        print(f"[deploy] 站点目录不存在: {SITE}", file=sys.stderr)
        return 1

    files = collect_files()
    if not files:
        print("[deploy] 站点目录为空", file=sys.stderr)
        return 1

    total_bytes = sum(p.stat().st_size for _, p in files)
    print(f"[deploy] 站点: {SITE}")
    print(f"[deploy] 文件数: {len(files)}  总大小: {total_bytes / 1024 / 1024:.2f} MB")
    print(f"[deploy] 项目: {PROJECT}  @ branch {BRANCH}")

    # 1) 创建 deployment（Direct Upload 携带文件哈希清单）
    hashes = [{"path": "/" + rel, "sha256": sha256_of(p)} for rel, p in files]
    created = api_ok(
        request("POST", f"{API}/deployments",
                {"branch": BRANCH, "file_hashes": hashes}),
        "创建 deployment",
    )
    deployment_id = created["id"]
    upload_url = created["url"]
    print(f"[deploy] deployment {deployment_id} 已创建，开始上传 {len(files)} 个文件…")

    # 2) 并行上传每个文件到 {upload_url}/{sha256}
    done = 0
    lock = None

    def upload_one(item: tuple[str, Path]) -> str:
        rel, path = item
        digest = sha256_of(path)
        with path.open("rb") as handle:
            data = handle.read()
        resp = request("PUT", f"{upload_url}/{digest}", raw=data,
                       content_type="application/octet-stream")
        if not resp.get("success"):
            raise RuntimeError(f"上传失败 {rel}: {resp}")
        return rel

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(upload_one, item): item for item in files}
        for future in concurrent.futures.as_completed(futures):
            rel = futures[future][0]
            try:
                future.result()
                done += 1
                if done % 25 == 0 or done == len(files):
                    print(f"[deploy] 已上传 {done}/{len(files)}")
            except Exception as exc:
                print(f"[deploy] 文件上传出错 {rel}: {exc}", file=sys.stderr)
                return 1

    # 3) 轮询 deployment 直到完成
    print("[deploy] 文件全部上传，等待部署完成…")
    for _ in range(60):
        time.sleep(5)
        status = api_ok(
            request("GET", f"{API}/deployments/{deployment_id}"), "查询状态")
        stage = (status.get("latest_stage") or {}).get("status", "?")
        if stage in ("success", "failed", "error"):
            if stage == "success":
                url = status.get("url", "?")
                print(f"[deploy] ✅ 部署成功: {url}")
                return 0
            print(f"[deploy] ❌ 部署状态: {stage}", file=sys.stderr)
            return 1
        print(f"[deploy]   部署中… stage={stage}")

    print("[deploy] 超时，部署未完成，请到 Cloudflare 控制台查看。", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
