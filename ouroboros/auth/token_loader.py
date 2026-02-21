"""
Token loader for OAuth and API keys from auth.json.

This module provides functions to load authentication tokens
from various sources (auth.json, env vars, etc.) for use with
different LLM providers.
"""

import base64
import json
import logging
import os
from pathlib import Path
from typing import Dict, Optional, Tuple

log = logging.getLogger(__name__)

# Default path to auth.json
DEFAULT_AUTH_PATH = Path.home() / ".openclaw" / "agents" / "main" / "agent" / "auth.json"


def decode_jwt_payload(token: str) -> Optional[Dict]:
    """
    Decode JWT payload without verification (for debugging/extracting claims).

    Args:
        token: JWT token string

    Returns:
        Decoded payload dict or None if decoding fails
    """
    try:
        # JWT has 3 parts: header.payload.signature
        parts = token.split(".")
        if len(parts) != 3:
            log.warning(f"Invalid JWT format")
            return None

        # Decode payload (base64url)
        payload_b64 = parts[1]
        # Add padding if needed
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding

        payload_json = base64.urlsafe_b64decode(payload_b64)
        payload = json.loads(payload_json)

        return payload

    except Exception as e:
        log.error(f"Failed to decode JWT: {e}")
        return None


def extract_account_id_from_jwt(token: str) -> Optional[str]:
    """
    Extract ChatGPT account_id from JWT token.

    The account_id is in: https://api.openai.com/auth -> chatgpt_account_id

    Args:
        token: JWT token string

    Returns:
        Account ID or None if not found
    """
    payload = decode_jwt_payload(token)
    if not payload:
        return None

    # Try different paths
    auth_info = payload.get("https://api.openai.com/auth", {})
    account_id = auth_info.get("chatgpt_account_id")

    if account_id:
        return account_id

    log.warning(f"Could not find chatgpt_account_id in JWT payload")
    return None


def load_openai_oauth_token(auth_path: Optional[Path] = None) -> Optional[str]:
    """
    Load OpenAI OAuth access token from auth.json.

    Args:
        auth_path: Path to auth.json (default: ~/.openclaw/agents/main/agent/auth.json)

    Returns:
        OAuth access token or None if not found
    """
    auth_path = auth_path or DEFAULT_AUTH_PATH

    if not auth_path.exists():
        log.debug(f"Auth file not found: {auth_path}")
        return None

    try:
        with open(auth_path, "r") as f:
            auth_data = json.load(f)

        # Try different structures
        # Structure 1: {"openai_oauth": {"access": "..."}}
        if "openai_oauth" in auth_data:
            return auth_data["openai_oauth"].get("access") or auth_data["openai_oauth"].get("access_token")

        # Structure 2: {"openai-codex": {"access": "..."}}
        if "openai-codex" in auth_data:
            return auth_data["openai-codex"].get("access") or auth_data["openai-codex"].get("access_token")

        # Structure 3: Flat {"access": "..."}
        if "access" in auth_data:
            return auth_data["access"]

        # Structure 4: Flat {"access_token": "..."}
        if "access_token" in auth_data:
            return auth_data["access_token"]

        log.warning(f"Could not find access_token in auth.json")
        return None

    except Exception as e:
        log.error(f"Failed to load OpenAI OAuth token: {e}")
        return None


def load_openai_oauth_with_account_id(auth_path: Optional[Path] = None) -> Optional[Tuple[str, str]]:
    """
    Load OpenAI OAuth access token and account_id from auth.json.

    Args:
        auth_path: Path to auth.json (default: ~/.openclaw/agents/main/agent/auth.json)

    Returns:
        Tuple of (access_token, account_id) or None if not found
    """
    auth_path = auth_path or DEFAULT_AUTH_PATH

    if not auth_path.exists():
        log.debug(f"Auth file not found: {auth_path}")
        return None

    try:
        with open(auth_path, "r") as f:
            auth_data = json.load(f)

        token = None
        account_id = None

        # Try different structures
        # Structure 1: {"openai_oauth": {"access": "...", "account_id": "..."}}
        if "openai_oauth" in auth_data:
            oauth_data = auth_data["openai_oauth"]
            token = oauth_data.get("access") or oauth_data.get("access_token")
            account_id = oauth_data.get("account_id")

        # Structure 2: {"openai-codex": {"access": "...", "account_id": "..."}}
        if "openai-codex" in auth_data:
            oauth_data = auth_data["openai-codex"]
            token = token or (oauth_data.get("access") or oauth_data.get("access_token"))
            account_id = account_id or oauth_data.get("account_id")

        # Fallback: extract from JWT
        if token and not account_id:
            account_id = extract_account_id_from_jwt(token)

        if token and account_id:
            return token, account_id

        log.warning(f"Could not find OpenAI OAuth token with account_id in auth.json")
        return None

    except Exception as e:
        log.error(f"Failed to load OpenAI OAuth token with account_id: {e}")
        return None


def load_api_key(provider: str, auth_path: Optional[Path] = None) -> Optional[str]:
    """
    Load API key for a provider from auth.json.

    Args:
        provider: Provider name (e.g., "zai", "opencode", "openrouter")
        auth_path: Path to auth.json (default: ~/.openclaw/agents/main/agent/auth.json)

    Returns:
        API key or None if not found
    """
    auth_path = auth_path or DEFAULT_AUTH_PATH

    # First check env var
    env_key = f"{provider.upper()}_API_KEY"
    env_value = os.getenv(env_key)
    if env_value:
        log.debug(f"Found {env_key} in environment")
        return env_value

    if not auth_path.exists():
        log.debug(f"Auth file not found: {auth_path}")
        return None

    try:
        with open(auth_path, "r") as f:
            auth_data = json.load(f)

        # Try to find the provider
        if provider in auth_data:
            provider_data = auth_data[provider]
            if isinstance(provider_data, dict):
                return provider_data.get("key")
            else:
                # Might be a raw string
                return str(provider_data)

        log.debug(f"Could not find API key for provider '{provider}' in auth.json")
        return None

    except Exception as e:
        log.error(f"Failed to load API key for '{provider}': {e}")
        return None


def load_all_tokens(auth_path: Optional[Path] = None) -> Dict[str, str]:
    """
    Load all available tokens from auth.json.

    This is useful for debugging and token discovery.

    Args:
        auth_path: Path to auth.json (default: ~/.openclaw/agents/main/agent/auth.json)

    Returns:
        Dict mapping provider/identifier to token
    """
    auth_path = auth_path or DEFAULT_AUTH_PATH
    tokens = {}

    if not auth_path.exists():
        log.debug(f"Auth file not found: {auth_path}")
        return tokens

    try:
        with open(auth_path, "r") as f:
            auth_data = json.load(f)

        for key, value in auth_data.items():
            if isinstance(value, dict):
                # Try to extract common fields
                if "access" in value:
                    tokens[f"{key}.access"] = value["access"]
                elif "access_token" in value:
                    tokens[f"{key}.access_token"] = value["access_token"]
                elif "key" in value:
                    tokens[f"{key}.key"] = value["key"]
                elif "token" in value:
                    tokens[f"{key}.token"] = value["token"]
            else:
                tokens[key] = str(value)

    except Exception as e:
        log.error(f"Failed to load all tokens: {e}")

    return tokens
