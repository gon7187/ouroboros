#!/usr/bin/env python3
"""OAuth authorization CLI for OpenAI Codex profile.

Supports two modes:
1) Refresh existing tokens (no browser)
2) Full browser OAuth flow (PKCE)
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from ouroboros.auth.oauth import OpenAIClient


OPENCLAW_DIR = Path.home() / ".openclaw"
OPENCLAW_CONFIG = OPENCLAW_DIR / "openclaw.json"
AUTH_PROFILES = OPENCLAW_DIR / "agents" / "main" / "agent" / "auth-profiles.json"
AUTH_JSON = OPENCLAW_DIR / "agents" / "main" / "agent" / "auth.json"


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _mask(value: str, head: int = 6, tail: int = 4) -> str:
    if not value:
        return ""
    if len(value) <= head + tail:
        return value
    return f"{value[:head]}...{value[-tail:]}"


def _decode_jwt_payload(token: str) -> Dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        return {}
    payload_b64 = parts[1]
    pad = (4 - (len(payload_b64) % 4)) % 4
    payload_b64 += "=" * pad
    try:
        payload_json = base64.urlsafe_b64decode(payload_b64.encode("utf-8")).decode("utf-8")
        return json.loads(payload_json)
    except Exception:
        return {}


def _get_codex_profile() -> Dict[str, Any]:
    obj = _load_json(AUTH_PROFILES)
    return obj.get("profiles", {}).get("openai-codex:default", {})


def detect_client_id() -> Optional[str]:
    import os

    env_id = (os.environ.get("OPENAI_OAUTH_CLIENT_ID") or "").strip()
    if env_id:
        return env_id

    cfg = _load_json(OPENCLAW_CONFIG)
    cfg_id = str(cfg.get("OPENAI_OAUTH_CLIENT_ID") or "").strip()
    if cfg_id:
        return cfg_id

    prof = _get_codex_profile()
    access = prof.get("access")
    if isinstance(access, str) and access:
        payload = _decode_jwt_payload(access)
        cid = str(payload.get("client_id") or "").strip()
        if cid:
            return cid

    return None


def save_codex_tokens(access: str, refresh: Optional[str], expires: Optional[int]) -> None:
    profiles = _load_json(AUTH_PROFILES)
    profiles.setdefault("version", 1)
    profiles.setdefault("profiles", {})
    profiles.setdefault("order", {})
    profiles.setdefault("lastGood", {})
    profiles.setdefault("usageStats", {})

    prev = profiles["profiles"].get("openai-codex:default", {})
    account_id = prev.get("accountId")
    if not account_id:
        payload = _decode_jwt_payload(access)
        auth_claim = payload.get("https://api.openai.com/auth")
        if isinstance(auth_claim, dict):
            account_id = auth_claim.get("chatgpt_account_id")

    entry: Dict[str, Any] = {
        "type": "oauth",
        "provider": "openai-codex",
        "access": access,
        "refresh": refresh,
        "expires": expires,
    }
    if account_id:
        entry["accountId"] = account_id

    profiles["profiles"]["openai-codex:default"] = entry
    profiles["order"].setdefault("openai-codex", ["openai-codex:default"])
    profiles["lastGood"]["openai-codex"] = "openai-codex:default"
    _save_json(AUTH_PROFILES, profiles)

    auth = _load_json(AUTH_JSON)
    auth["openai-codex"] = {
        "type": "oauth",
        "access": access,
        "refresh": refresh,
        "expires": expires,
    }
    _save_json(AUTH_JSON, auth)


def refresh_existing() -> bool:
    prof = _get_codex_profile()
    access = str(prof.get("access") or "")
    refresh = str(prof.get("refresh") or "")
    if not access or not refresh:
        print("No existing openai-codex access/refresh found")
        return False

    payload = _decode_jwt_payload(access)
    client_id = str(payload.get("client_id") or "").strip()
    if not client_id:
        print("Cannot refresh: missing client_id in stored JWT")
        return False

    print(f"Refreshing with client_id: {_mask(client_id)}")
    client = OpenAIClient(client_id=client_id)
    tokens = client.refresh_tokens(refresh)
    save_codex_tokens(tokens.access_token, tokens.refresh_token or refresh, tokens.expires_at)

    print("OK: token refreshed")
    if tokens.expires_at:
        print(f"Expires in: {(tokens.expires_at - int(time.time())) / 3600:.1f}h")
    return True


def browser_flow() -> int:
    print("=" * 64)
    print("OpenAI Codex OAuth Login (Browser)")
    print("=" * 64)

    detected = detect_client_id()
    if detected:
        print(f"Detected client_id: {_mask(detected)}")
        raw = input("Press Enter to use it or paste another client_id: ").strip()
        client_id = raw or detected
    else:
        print("No client_id auto-detected.")
        client_id = input("Paste OpenAI OAuth client_id: ").strip()

    if not client_id:
        print("ERROR: client_id is required")
        return 1

    import os
    default_redirect = (os.environ.get("OPENAI_OAUTH_REDIRECT_URI") or "").strip() or "http://localhost:3000/callback"
    redirect_uri = input(f"Redirect URI [{default_redirect}]: ").strip() or default_redirect

    client = OpenAIClient(client_id=client_id, redirect_uri=redirect_uri)
    auth_url = client.get_authorization_url()

    print("\n1) Open URL in browser:\n")
    print(auth_url)
    print("\n2) Complete login and consent")
    print("3) Paste FULL redirect URL below\n")

    redirect_url = input("Redirect URL: ").strip()
    if not redirect_url:
        print("ERROR: redirect URL is required")
        return 1

    try:
        tokens = client.exchange_code_for_tokens(redirect_url)
    except Exception as exc:
        print(f"ERROR: token exchange failed: {exc}")
        return 1

    save_codex_tokens(tokens.access_token, tokens.refresh_token, tokens.expires_at)
    print("OK: tokens saved for openai-codex")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="OpenAI Codex OAuth helper")
    parser.add_argument("--refresh-only", action="store_true", help="Refresh existing token without browser")
    args = parser.parse_args()

    if args.refresh_only:
        return 0 if refresh_existing() else 1

    print("Try refresh-only first? [Y/n]: ", end="")
    ans = input().strip().lower()
    if ans in ("", "y", "yes"):
        if refresh_existing():
            return 0
        print("Refresh-only failed; falling back to browser flow.\n")

    return browser_flow()


if __name__ == "__main__":
    raise SystemExit(main())
