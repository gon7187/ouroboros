"""
Token loader for OAuth and API keys from auth.json.

Loads authentication tokens from ~/.openclaw/agents/main/agent/auth.json
"""

import json
import logging
import os
from pathlib import Path
from typing import Dict, Optional, Any

log = logging.getLogger(__name__)


DEFAULT_AUTH_PATH = Path.home() / ".openclaw" / "agents" / "main" / "agent" / "auth.json"


def load_oauth_tokens(auth_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Load OAuth tokens from auth.json file.

    Args:
        auth_path: Path to auth.json file (default: ~/.openclaw/agents/main/agent/auth.json)

    Returns:
        Dict with provider names as keys and token data as values
    """
    auth_path = auth_path or DEFAULT_AUTH_PATH

    if not auth_path.exists():
        log.warning(f"Auth file not found: {auth_path}")
        return {}

    try:
        with open(auth_path, "r") as f:
            data = json.load(f)

        # Extract only OAuth entries
        oauth_entries = {}
        for provider, auth_data in data.items():
            if isinstance(auth_data, dict) and auth_data.get("type") == "oauth":
                oauth_entries[provider] = auth_data

        log.info(f"Loaded {len(oauth_entries)} OAuth entries from {auth_path}")
        return oauth_entries

    except Exception as e:
        log.error(f"Failed to load auth file: {e}")
        return {}


def get_codex_token(auth_path: Optional[Path] = None) -> Optional[str]:
    """
    Get Codex OAuth access token from auth.json.

    Args:
        auth_path: Path to auth.json file

    Returns:
        Access token string, or None if not found
    """
    oauth_entries = load_oauth_tokens(auth_path)

    codex_entry = oauth_entries.get("openai-codex")
    if not codex_entry:
        return None

    return codex_entry.get("access")


def get_codex_account_id(auth_path: Optional[Path] = None) -> Optional[str]:
    """
    Get Codex account ID from JWT token.

    Args:
        auth_path: Path to auth.json file

    Returns:
        Account ID string, or None if not found
    """
    oauth_entries = load_oauth_tokens(auth_path)

    codex_entry = oauth_entries.get("openai-codex")
    if not codex_entry:
        return None

    # Try to extract from JWT
    access_token = codex_entry.get("access")
    if not access_token:
        return None

    try:
        import base64

        # Decode JWT (without signature verification)
        parts = access_token.split(".")
        if len(parts) != 3:
            return None

        payload = parts[1]
        payload += "=" * ((4 - len(payload) % 4) % 4)

        decoded = base64.urlsafe_b64decode(payload)
        jwt_data = json.loads(decoded)

        # Try different account ID fields
        return (
            jwt_data.get("https://api.openai.com/auth", {}).get("chatgpt_account_id") or
            jwt_data.get("chatgpt_account_id") or
            jwt_data.get("https://api.openai.com/auth", {}).get("user_id") or
            jwt_data.get("sub")
        )

    except Exception as e:
        log.debug(f"Failed to extract account_id from JWT: {e}")
        return None


def load_api_keys(auth_path: Optional[Path] = None) -> Dict[str, str]:
    """
    Load API keys from auth.json file.

    Args:
        auth_path: Path to auth.json file

    Returns:
        Dict with provider names as keys and API keys as values
    """
    auth_path = auth_path or DEFAULT_AUTH_PATH

    if not auth_path.exists():
        log.warning(f"Auth file not found: {auth_path}")
        return {}

    try:
        with open(auth_path, "r") as f:
            data = json.load(f)

        # Extract only API key entries
        api_key_entries = {}
        for provider, auth_data in data.items():
            if isinstance(auth_data, dict) and auth_data.get("type") == "api_key":
                api_key_entries[provider] = auth_data.get("key")

        log.info(f"Loaded {len(api_key_entries)} API keys from {auth_path}")
        return api_key_entries

    except Exception as e:
        log.error(f"Failed to load auth file: {e}")
        return {}
