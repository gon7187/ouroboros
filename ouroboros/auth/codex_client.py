"""
Codex Backend API Client.

OpenAI Codex uses a different API endpoint than the standard OpenAI API:
- Standard: https://api.openai.com/v1/chat/completions
- Codex backend: https://chatgpt.com/backend-api/codex/responses

This client handles the backend API format with:
- OAuth token authentication
- Specific headers (chatgpt-account-id, OpenAI-Beta, originator)
- Required 'input' field in request
- 'store' field must be set to false
- 'stream' field must be set to true (SSE format)
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
        stream: bool = True,  # Codex backend requires streaming
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Make a chat completion request to Codex backend API.

        Note: Codex backend API requires:
        - 'input' field (not 'messages')
        - 'store' field must be set to false
        - 'stream' field must be set to true

        Args:
            messages: Chat messages (OpenAI format: [{"role": "user", "content": "..."}])
            model: Model name (default: gpt-5.3-codex)
            stream: Whether to stream response (Codex backend requires True)
            **kwargs: Additional parameters (temperature, max_tokens, etc.)

        Returns:
            Response dict with 'content', 'usage', etc.
        """
        url = f"{self.base_url}{self.CODEX_ENDPOINT}"

        # Convert OpenAI-style messages to input format
        # Codex backend uses 'input' which is a single string
        input_text = self._messages_to_input(messages)

        # Build request payload
        payload = {
            "input": input_text,
            "model": model,
            "store": False,  # Required by Codex backend API
            "stream": True,   # Codex backend requires streaming
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
        log.debug(f"Input preview: {input_text[:200]}...")

        try:
            response = self._client.post(url, json=payload)
            response.raise_for_status()

            # Parse response (always SSE for Codex backend)
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

    def _messages_to_input(self, messages: List[Dict[str, Any]]) -> str:
        """
        Convert OpenAI-style messages to input string.

        Codex backend API expects a single 'input' string, not 'messages'.

        Args:
            messages: OpenAI-style messages (role + content)

        Returns:
            Single input string
        """
        input_parts = []

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "system":
                input_parts.append(f"System: {content}")
            elif role == "user":
                input_parts.append(f"User: {content}")
            elif role == "assistant":
                input_parts.append(f"Assistant: {content}")
            elif role == "function" or role == "tool":
                # Skip function/tool messages for now
                continue
            else:
                # Unknown role, just include the content
                input_parts.append(content)

        # Join with newlines
        input_text = "\n\n".join(input_parts)

        return input_text

    def _parse_response(self, response_text: str) -> Dict[str, Any]:
        """
        Parse response from Codex backend API.

        The response format is SSE (Server-Sent Events), not standard JSON.
        We need to extract content and usage from SSE events.

        Args:
            response_text: Raw response text (SSE format)

        Returns:
            Parsed dict with 'content', 'usage', etc.
        """
        # Codex backend always returns SSE format
        return self._parse_sse_response(response_text)

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
