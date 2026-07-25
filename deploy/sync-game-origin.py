#!/usr/bin/env python3
"""Sync GAME_ORIGIN onto Cloudflare Pages production env vars."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


def main() -> int:
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    origin = os.environ.get("GAME_ORIGIN", "").strip().rstrip("/")
    if not token or not account:
        print("CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID are required", file=sys.stderr)
        return 1
    if not origin:
        print("GAME_ORIGIN empty; skipping sync")
        return 0

    url = (
        f"https://api.cloudflare.com/client/v4/accounts/{account}"
        "/pages/projects/chessvisionharness"
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req) as resp:
        data = json.load(resp)
    if not data.get("success"):
        print(data, file=sys.stderr)
        return 1

    prod = ((data.get("result") or {}).get("deployment_configs") or {}).get("production") or {}
    env_vars = dict(prod.get("env_vars") or {})
    env_vars["GAME_ORIGIN"] = {"type": "plain_text", "value": origin}

    payload = {"deployment_configs": {"production": {"env_vars": env_vars}}}
    body = json.dumps(payload).encode()
    patch = urllib.request.Request(url, data=body, headers=headers, method="PATCH")
    try:
        with urllib.request.urlopen(patch) as resp:
            out = json.load(resp)
    except urllib.error.HTTPError as err:
        detail = err.read().decode("utf-8", errors="replace")
        print(f"HTTP {err.code}: {detail}", file=sys.stderr)
        return 1

    if not out.get("success"):
        print(out, file=sys.stderr)
        return 1

    print(f"GAME_ORIGIN synced for production: {origin}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
