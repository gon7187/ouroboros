"""
SSE (Server-Sent Events) Parser.

Handles different SSE formats from various LLM providers:
- OpenAI standard format (data: {"choices": [...], "usage": {...}})
- OpenAI Codex backend format (data: {"type": "content", "delta": "..."})
- Generic SSE format (data: JSON)

Supports:
- Line-by-line parsing
- JSON extraction
- Delta content accumulation
- Usage extraction
- End-of-stream detection
"""

import json
import logging
from typing import Any, Dict, Generator, List, Optional, Tuple

log = logging.getLogger(__name__)


def parse_sse_line(line: str) -> Optional[Dict[str, Any]]:
    """
    Parse a single SSE line.

    Args:
        line: Raw SSE line (e.g., "data: {...}")

    Returns:
        Parsed JSON dict or None if not a data line
    """
    line = line.strip()

    # Skip empty lines and comments
    if not line or line.startswith(":"):
        return None

    # Extract JSON after "data: " prefix
    if line.startswith("data: "):
        json_str = line[6:]  # Remove "data: " prefix
        json_str = json_str.strip()

        # Check for end marker
        if json_str == "[DONE]":
            return {"__done__": True}

        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            log.debug(f"Failed to parse SSE JSON: {e}, line: {line[:100]}")
            return None

    return None


class SSEParser:
    """
    Parse streaming responses in SSE format.

    Handles multiple provider formats:
    - OpenAI standard: {"choices": [{"delta": {"content": "..."}}]}
    - Codex backend: {"type": "content", "delta": "..."}
    - Generic: any JSON structure
    """

    def __init__(self):
        self.content_parts: List[str] = []
        self.usage: Dict[str, int] = {}
        self.is_done = False

    def feed(self, data: str) -> None:
        """
        Feed raw SSE data to the parser.

        Args:
            data: Raw SSE response text (multiple lines)
        """
        lines = data.split("\n")

        for line in lines:
            event = parse_sse_line(line)

            if event is None:
                continue

            # Check for end marker
            if event.get("__done__"):
                self.is_done = True
                continue

            # Parse content based on format
            self._extract_content(event)
            self._extract_usage(event)

    def _extract_content(self, event: Dict[str, Any]) -> None:
        """
        Extract content delta from event.

        Handles multiple formats:
        - OpenAI: event["choices"][0]["delta"]["content"]
        - Codex: event["delta"] or event["choices"][0]["delta"]["content"]
        """
        content = None

        # Format 1: OpenAI standard
        if "choices" in event and len(event["choices"]) > 0:
            choice = event["choices"][0]
            if "delta" in choice and "content" in choice["delta"]:
                content = choice["delta"]["content"]
            elif "message" in choice and "content" in choice["message"]:
                content = choice["message"]["content"]

        # Format 2: Codex backend (type + delta)
        elif "type" in event:
            if event["type"] == "content":
                content = event.get("delta")

        # Format 3: Direct delta field
        elif "delta" in event:
            delta = event["delta"]
            if isinstance(delta, str):
                content = delta
            elif isinstance(delta, dict) and "content" in delta:
                content = delta["content"]

        if content:
            self.content_parts.append(content)

    def _extract_usage(self, event: Dict[str, Any]) -> None:
        """
        Extract usage information from event.

        Usage is usually in the last event.
        """
        if "usage" in event:
            usage_data = event["usage"]
            self.usage = {
                "prompt_tokens": usage_data.get("prompt_tokens", 0),
                "completion_tokens": usage_data.get("completion_tokens", 0),
                "total_tokens": usage_data.get("total_tokens", 0),
            }

    def get_content(self) -> str:
        """Get accumulated content."""
        return "".join(self.content_parts)

    def get_usage(self) -> Dict[str, int]:
        """Get usage information."""
        return self.usage

    def is_stream_done(self) -> bool:
        """Check if stream is complete."""
        return self.is_done

    def reset(self) -> None:
        """Reset parser state."""
        self.content_parts = []
        self.usage = {}
        self.is_done = False


def parse_sse_stream(response_text: str) -> Dict[str, Any]:
    """
    Parse complete SSE response text.

    Convenience function for non-streaming scenarios.

    Args:
        response_text: Raw SSE response text

    Returns:
        Dict with 'content' and 'usage'
    """
    parser = SSEParser()
    parser.feed(response_text)

    return {
        "content": parser.get_content(),
        "usage": parser.get_usage(),
    }


def stream_sse_chunks(response_text: str) -> Generator[Dict[str, Any], None, None]:
    """
    Stream SSE response as chunks.

    Generator that yields each parsed event.

    Args:
        response_text: Raw SSE response text

    Yields:
        Parsed event dicts
    """
    lines = response_text.split("\n")

    for line in lines:
        event = parse_sse_line(line)
        if event:
            yield event
