"""
Codex Backend API Client.

OpenAI Codex uses a different API endpoint than the standard OpenAI API:
- Standard: https://api.openai.com/v1/chat/completions
- Codex backend: https://chatgpt.com/backend-api/codex/responses

This client handles the backend API format with:
- OAuth token authentication
- Specific headers (chatgpt-account-id, OpenAI-Beta, originator)
- Streaming response handling (SSE format)
"""

import json
import logging
from typing import Any, Dict, List, Optional

import httpx

log = logging.getLogger(__name__)


class CodexBackendClient:
    """
    Client for OpenAI Codex backend API.

    Uses OAuth token and backend-api endpoint.
    """

    DEFAULT_BASE_URL = "https://chatgpt.com/backend-api"
    CODEX_ENDPOINT = "/codex/responses"

    def __init__(
        self,
        access_token: str,
        account_id: str,
        base_url: Optional[str] = None,
    ):
        """
        Initialize Codex backend client.

        Args:
            access_token: OAuth access token
            account_id: Account ID from JWT payload
            base_url: Base URL (default: https://chatgpt.com/backend-api)
        """
        self.access_token = access_token
        self.account_id = account_id
        self.base_url = base_url or self.DEFAULT_BASE_URL

        self._client = httpx.Client(
            timeout=120.0,
            headers={
                "Authorization": f"Bearer {access_token}",
                "chatgpt-account-id": account_id,
                "OpenAI-Beta": "responses=experimental",
                "originator": "pi",
                "User-Agent": "pi (Ubuntu 22.04.4 LTS)",
                "Content-Type": "application/json",
            },
        )

    def chat(
        self,
        messages: List[Dict[str, Any]],
        model: str = "gpt-5.3-codex",
        stream: bool = False,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Make a chat completion request to Codex backend API.

        Args:
            messages: Chat messages (OpenAI format)
            model: Model name (default: gpt-5.3-codex)
            stream: Whether to stream response (not yet implemented)
            **kwargs: Additional parameters (temperature, max_tokens, etc.)

        Returns:
            Response dict with 'content', 'usage', etc.
        """
        url = f"{self.base_url}{self.CODEX_ENDPOINT}"

        # Build request payload
        payload = {
            "messages": messages,
            "model": model,
        }

        # Add optional parameters
        if "temperature" in kwargs:
            payload["temperature"] = kwargs["temperature"]
        if "max_tokens" in kwargs:
            payload["max_tokens"] = kwargs["max_tokens"]
        if "top_p" in kwargs:
            payload["top_p"] = kwargs["top_p"]

        log.debug(f"Codex backend request: {url}")
        log.debug(f"Payload keys: {list(payload.keys())}")

        try:
            response = self._client.post(url, json=payload)
            response.raise_for_status()

            # Parse response
            result = self._parse_response(response.text)

            log.debug(f"Codex backend response: content length={len(result.get('content', ''))}")
            log.debug(f"Usage: {result.get('usage', {})}")

            return result

        except httpx.HTTPStatusError as e:
            log.error(f"Codex backend HTTP error: {e.response.status_code}")
            log.error(f"Response body: {e.response.text[:500]}")
            raise
        except Exception as e:
            log.error(f"Codex backend error: {e}")
            raise

    def _parse_response(self, response_text: str) -> Dict[str, Any]:
        """
        Parse response from Codex backend API.

        The response format is not standard OpenAI format.
        We need to extract content and usage.

        Args:
            response_text: Raw response text

        Returns:
            Parsed dict with 'content', 'usage', etc.
        """
        # Try to parse as JSON first
        try:
            data = json.loads(response_text)
        except json.JSONDecodeError:
            log.warning(f"Failed to parse response as JSON, length={len(response_text)}")
            log.debug(f"Response preview: {response_text[:500]}")
            return {
                "content": response_text,
                "usage": {},
            }

        # Check if this is an SSE stream response
        # SSE responses are line-by-line with "data:" prefix
        if "data:" in response_text or "\n\n" in response_text:
            return self._parse_sse_response(response_text)

        # Standard JSON response (if any)
        # Try to extract content
        content = None
        usage = {}

        # Different possible structures
        if "message" in data:
            content = data["message"].get("content")
        elif "content" in data:
            content = data["content"]
        elif "choices" in data and len(data["choices"]) > 0:
            # OpenAI-style format
            choice = data["choices"][0]
            if "message" in choice:
                content = choice["message"].get("content")

        # Try to extract usage
        if "usage" in data:
            usage_data = data["usage"]
            usage = {
                "prompt_tokens": usage_data.get("prompt_tokens", 0),
                "completion_tokens": usage_data.get("completion_tokens", 0),
                "total_tokens": usage_data.get("total_tokens", 0),
            }

        if content is None:
            # Fallback: just return the raw data
            log.warning(f"Could not extract content from response: {list(data.keys())}")
            content = json.dumps(data, indent=2)

        return {
            "content": content,
            "usage": usage,
            "raw": data,
        }

    def _parse_sse_response(self, response_text: str) -> Dict[str, Any]:
        """
        Parse SSE (Server-Sent Events) stream response.

        SSE format:
        ```
        data: {...}
        data: {...}
        data: [DONE]
        ```

        Args:
            response_text: Raw SSE response text

        Returns:
            Combined content from all events
        """
        # Split by "data:" prefix
        lines = response_text.split("data:")

        content_parts = []
        usage = {}

        for line in lines:
            line = line.strip()
            if not line or line == "[DONE]":
                continue

            try:
                data = json.loads(line)

                # Extract content
                if "choices" in data and len(data["choices"]) > 0:
                    choice = data["choices"][0]
                    if "delta" in choice:
                        delta = choice["delta"]
                        if "content" in delta:
                            content_parts.append(delta["content"])
                    elif "message" in choice:
                        message = choice["message"]
                        if "content" in message:
                            content_parts.append(message["content"])

                # Extract usage (usually in last message)
                if "usage" in data:
                    usage_data = data["usage"]
                    usage = {
                        "prompt_tokens": usage_data.get("prompt_tokens", 0),
                        "completion_tokens": usage_data.get("completion_tokens", 0),
                        "total_tokens": usage_data.get("total_tokens", 0),
                    }

            except json.JSONDecodeError as e:
                log.debug(f"Failed to parse SSE line: {e}")
                continue

        content = "".join(content_parts)

        return {
            "content": content,
            "usage": usage,
        }

    def close(self):
        """Close the HTTP client."""
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def create_codex_client(
    access_token: str,
    account_id: Optional[str] = None,
) -> CodexBackendClient:
    """
    Factory function to create Codex backend client.

    If account_id is not provided, try to extract it from the access token JWT.

    Args:
        access_token: OAuth access token
        account_id: Optional account ID (if not provided, extracted from JWT)

    Returns:
        CodexBackendClient instance
    """
    if not account_id:
        # Try to extract account_id from JWT
        # Note: This is a simple JWT decode without signature verification
        # Just for extracting the account_id
        try:
            parts = access_token.split(".")
            if len(parts) == 3:
                payload = parts[1]
                # Add padding if needed
                payload += "=" * ((4 - len(payload) % 4) % 4)
                import base64
                decoded = base64.urlsafe_b64decode(payload)
                jwt_data = json.loads(decoded)

                # Try different account ID fields
                account_id = (
                    jwt_data.get("account_id") or
                    jwt_data.get("sub") or
                    jwt_data.get("https://api.openai.com/auth", {}).get("user_id") or
                    jwt_data.get("email")
                )

                if account_id:
                    log.info(f"Extracted account_id from JWT: {account_id}")
                else:
                    log.warning("Could not extract account_id from JWT, using email as fallback")

        except Exception as e:
            log.warning(f"Failed to extract account_id from JWT: {e}")

    if not account_id:
        # Fallback: use email from JWT or a default
        log.warning("No account_id provided or extracted, using default")
        account_id = "unknown"

    return CodexBackendClient(access_token, account_id)