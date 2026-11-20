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
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        # Cloudflare blocks requests with no/odd user agents (error 1010);
        # send a real browser UA so the asset upload endpoints accept us.
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/124.0 Safari/537.36"),
    }
    data = None
    if raw is not None:
        data = raw
        headers["Content-Type"] = content_type
    elif payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = content_type
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
    except urllib.error.HTTPError as exc:
        # Surface the API error body (Cloudflare returns a JSON error envelope)
        # instead of failing with a bare "HTTP 400" traceback.
        detail = exc.read().decode("utf-8", "replace")
        print(f"[deploy] HTTP {exc.code} from {url}", file=sys.stderr)
        print(detail[:600], file=sys.stderr)
        raise
    try:
        return json.loads(body.decode("utf-8"))
    except Exception:
        return {"success": False, "raw": body[:300].decode("utf-8", "replace")}


def multipart_form(fields: dict[str, str]) -> tuple[bytes, str]:
    """Encode ``fields`` as a ``multipart/form-data`` body and return
    ``(body, content_type)``.  The Cloudflare Pages API accepts the
    deployment parameters as form fields (NOT as a JSON body), so the
    ``manifest`` must be sent this way.
    """
    boundary = "----opencode" + hashlib.sha256(os.urandom(16)).hexdigest()[:16]
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        chunks.append(value.encode("utf-8"))
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Disable automatic redirects so a 302 to a presigned upload URL is
    returned to the caller (which then re-PUTs the bytes there)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def api_ok(resp: dict, what: str) -> dict:
    if not resp.get("success"):
        errors = resp.get("errors") or resp.get("raw") or resp
        print(f"[deploy] {what} failed: {json.dumps(errors, ensure_ascii=False)}",
              file=sys.stderr)
        sys.exit(1)
    return resp["result"]


def _is_access_login(target: str | None) -> bool:
    """True when a redirect points at the Cloudflare Access login flow instead
    of a presigned storage URL.

    Access-wrapped Pages projects answer the Direct Upload PUT with a 302 to
    ``/cdn-cgi/access/login/...`` rather than the storage endpoint, so the
    API-only upload can never complete and ``deploy.py`` must fall back.
    """
    if not target:
        return False
    return "cloudflareaccess.com" in target and "/cdn-cgi/access/" in target


class UploadBlockedError(RuntimeError):
    """Raised when the Direct Upload API is redirected to the Access login."""


def fallback_wrangler() -> int:
    """Deploy through ``wrangler pages deploy``.

    ``wrangler`` authenticates with the API token and talks to the Pages
    storage directly, so Cloudflare Access does not block it; the Direct
    Upload API in the same situation has no usable ``upload_url`` (or is
    redirected to the Access login).  Called automatically when the API upload
    cannot proceed.
    """
    import shutil
    import subprocess

    wrangler = shutil.which("wrangler")
    if not wrangler:
        print(
            "[deploy] Direct Upload blocked (the project is likely behind "
            "Cloudflare Access) and wrangler is not installed; run "
            "tools/deploy_website.ps1 instead.",
            file=sys.stderr,
        )
        return 1
    print("[deploy] Direct Upload blocked by Cloudflare Access; falling back "
          "to wrangler pages deploy...")
    os.environ["CLOUDFLARE_ACCOUNT_ID"] = ACCOUNT
    os.environ["CLOUDFLARE_API_TOKEN"] = TOKEN
    command = [
        wrangler, "pages", "deploy", str(SITE),
        f"--project-name={PROJECT}", f"--branch={BRANCH}",
        "--commit-dirty=true",
    ]
    proc = subprocess.run(command)
    return 0 if proc.returncode == 0 else 1


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

    # 1) Create the deployment.  The Cloudflare Pages API takes the Direct
    #    Upload parameters as *form fields* (multipart/form-data), not as a
    #    JSON body.  ``manifest`` is a JSON-encoded object of path -> sha256
    #    (paths WITHOUT a leading slash, as the API example shows).
    manifest = {rel: sha256_of(p) for rel, p in files}
    manifest_json = json.dumps(manifest, separators=(",", ":"))
    body, content_type = multipart_form({
        "branch": BRANCH,
        "commit_dirty": "false",
        "manifest": manifest_json,
        "pages_build_output_dir": ".",
    })
    created = api_ok(
        request("POST", f"{API}/deployments", raw=body, content_type=content_type),
        "Create deployment",
    )
    deployment_id = created["id"]
    upload_url = created.get("upload_url")
    if not upload_url:
        # No dedicated upload endpoint.  Access-wrapped projects omit it, and
        # falling back to the deployment ``url`` (pages.dev) only reaches the
        # Access login; go straight to wrangler instead of failing obscurely.
        print("[deploy] Deployment %s created but the API returned no "
              "upload_url; using wrangler." % deployment_id)
        return fallback_wrangler()
    print(f"[deploy] Deployment {deployment_id} created; uploading {len(files)} files...")

    # 2) Upload each file.  The first PUT to {upload_url}/{sha256} answers with
    #    a 302 to a presigned storage URL; we then PUT the same bytes there
    #    (no Authorization needed -- the presigned URL carries its own signature)
    #    and the request must stay a PUT (urllib would otherwise turn the 302
    #    into a GET).
    done = 0

    def put_no_redirect(url: str, data: bytes, headers: dict) -> tuple[int, dict]:
        req = urllib.request.Request(url, data=data, method="PUT", headers=headers)
        opener = urllib.request.build_opener(_NoRedirect())
        try:
            with opener.open(req, timeout=TIMEOUT) as resp:
                return resp.status, dict(resp.headers)
        except urllib.error.HTTPError as exc:
            # 302/307/308 surface here when redirect handling is disabled.
            return exc.code, dict(exc.headers)

    def upload_one(item: tuple[str, Path]) -> str:
        rel, path = item
        digest = sha256_of(path)
        with path.open("rb") as handle:
            data = handle.read()
        headers = {
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/octet-stream",
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/124.0 Safari/537.36"),
        }
        code, resp_headers = put_no_redirect(f"{upload_url}/{digest}", data, headers)
        if code in (301, 302, 303, 307, 308):
            target = resp_headers.get("Location") or resp_headers.get("location")
            if not target:
                raise RuntimeError(f"Redirect without Location for {rel}")
            if _is_access_login(target):
                raise UploadBlockedError()
            # Presigned URL: strip the now-invalid Authorization header.
            presigned_headers = {k: v for k, v in headers.items()
                                 if k.lower() != "authorization"}
            code, _ = put_no_redirect(target, data, presigned_headers)
        if code not in (200, 201, 204):
            raise RuntimeError(f"Upload failed {rel}: HTTP {code}")
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
            except UploadBlockedError:
                print("[deploy] Upload redirected to the Cloudflare Access "
                      "login; falling back to wrangler.")
                pool.shutdown(wait=False, cancel_futures=True)
                return fallback_wrangler()
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
