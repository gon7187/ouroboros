"""
Ouroboros — LLM client with multi-provider support.

Simplified to focus on LLM calls (chat, vision). Provider configuration
and model selection are extracted into clear, testable components.

Key principles:
- LLM-first: the client just calls LLMs, doesn't hide complexity
- Clear separation: provider config vs. LLM operations
- Minimal state: configuration is set once, then used
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from openai import OpenAI

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Provider Configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ProviderConfig:
    """Configuration for a single LLM provider."""
    name: str
    api_key: str
    base_url: Optional[str] = None
    requires_reasoning_effort: bool = True


@dataclass(frozen=True)
class ModelProfile:
    """Configuration for a task-specific model profile."""
    model: str
    effort: str
    temperature: float = 0.0
    max_tokens: int = 4096


# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------

_PRICING_STATIC: Dict[str, Tuple[float, float, float]] = {
    "anthropic/claude-opus-4.6": (5.0, 0.5, 25.0),
    "anthropic/claude-opus-4": (15.0, 1.5, 75.0),
    "anthropic/claude-sonnet-4": (3.0, 0.30, 15.0),
    "anthropic/claude-sonnet-4.6": (3.0, 0.30, 15.0),
    "anthropic/claude-sonnet-4.5": (3.0, 0.30, 15.0),
    "openai/o3": (2.0, 0.50, 8.0),
    "openai/o3-pro": (20.0, 1.0, 80.0),
    "openai/o4-mini": (1.10, 0.275, 4.40),
    "openai/gpt-4.1": (2.0, 0.50, 8.0),
    "openai/gpt-5.2": (1.75, 0.175, 14.0),
    "openai/gpt-5.2-codex": (1.75, 0.175, 14.0),
    "google/gemini-2.5-pro-preview": (1.25, 0.125, 10.0),
    "google/gemini-3-pro-preview": (2.0, 0.20, 12.0),
    "x-ai/grok-3-mini": (0.30, 0.03, 0.50),
    "qwen/qwen3.5-plus-02-15": (0.40, 0.04, 2.40),
    "glm/glm-5": (0.002, 0.002, 0.002),
    "glm/glm-4.7": (0.001, 0.001, 0.001),
    "glm/glm-4.7-flashx": (0.0004, 0.0004, 0.0004),
}


# ---------------------------------------------------------------------------
# Model Profiles
# ---------------------------------------------------------------------------

_MODEL_PROFILES: Dict[str, ModelProfile] = {
    "default": ModelProfile(model="glm/glm-4.7", effort="medium", temperature=0.0),
    "light": ModelProfile(model="glm/glm-4.7-flashx", effort="low", temperature=0.0),
    "code_task": ModelProfile(model="glm/glm-5", effort="medium", temperature=0.0),
    "analysis": ModelProfile(model="glm/glm-5", effort="high", temperature=0.0),
    "consciousness": ModelProfile(model="glm/glm-4.7-flashx", effort="low", temperature=0.0),
}


# ---------------------------------------------------------------------------
# Utility Functions
# ---------------------------------------------------------------------------

def normalize_reasoning_effort(effort: str, default: str = "medium") -> str:
    """Normalize reasoning effort to valid values."""
    valid = {"low", "medium", "high", "xhigh"}
    return effort if effort in valid else default


def reasoning_rank(effort: str) -> int:
    """Get numeric rank for reasoning effort (higher = more reasoning)."""
    return {"low": 0, "medium": 1, "high": 2, "xhigh": 3}.get(effort, 1)


def add_usage(total: Dict[str, Any], usage: Dict[str, Any]) -> None:
    """Add usage from one call to running total."""
    for key in ("prompt_tokens", "completion_tokens", "cached_tokens", "total_tokens"):
        total[key] = (total.get(key, 0) or 0) + (usage.get(key, 0) or 0)


# ---------------------------------------------------------------------------
# LLM Client
# ---------------------------------------------------------------------------

class LLMClient:
    """
    Simple LLM client for chat and vision queries.

    Responsibilities:
    - Manage provider configuration
    - Select models based on task type
    - Make chat and vision calls
    - Format tool calls for LLM

    Not responsible for:
    - Tool execution (handled by ToolRegistry)
    - Context building (handled by context.py)
    - Loop orchestration (handled by loop.py)
    """

    def __init__(self):
        self._providers: Dict[str, ProviderConfig] = {}
        self._clients: Dict[str, OpenAI] = {}
        self._active_provider: str = "openrouter"
        self._load_providers()

    def _load_providers(self) -> None:
        """Load provider configurations from environment."""
        # OpenRouter (primary)
        or_key = os.environ.get("OPENROUTER_API_KEY", "")
        if or_key:
            self._providers["openrouter"] = ProviderConfig(
                name="openrouter",
                api_key=or_key,
                base_url="https://openrouter.ai/api/v1",
                requires_reasoning_effort=True,
            )

        # Z.ai
        zai_key = os.environ.get("ZAI_API_KEY", "")
        if zai_key:
            self._providers["zai"] = ProviderConfig(
                name="zai",
                api_key=zai_key,
                base_url=os.environ.get("ZAI_BASE_URL", "https://api.z.ai/api/coding/paas/v4"),
                requires_reasoning_effort=False,
            )

        # OpenAI Codex
        codex_key = os.environ.get("OPENAI_CODEX_KEY", "")
        if codex_key:
            self._providers["codex"] = ProviderConfig(
                name="codex",
                api_key=codex_key,
                base_url=os.environ.get("OPENAI_CODEX_BASE_URL"),
                requires_reasoning_effort=True,
            )

        # OpenCode
        oc_key = os.environ.get("OPENCODE_API_KEY", "")
        if oc_key:
            self._providers["opencode"] = ProviderConfig(
                name="opencode",
                api_key=oc_key,
                base_url=os.environ.get("OPENCODE_BASE_URL"),
                requires_reasoning_effort=False,
            )

        # Set active provider
        if not self._providers:
            log.warning("No LLM providers configured!")
        elif "openrouter" in self._providers:
            self._active_provider = "openrouter"
        else:
            self._active_provider = next(iter(self._providers.keys()))

        log.info(f"Loaded {len(self._providers)} LLM provider(s), active: {self._active_provider}")

    def _get_client(self, provider: Optional[str] = None) -> Tuple[OpenAI, ProviderConfig]:
        """Get or create OpenAI client for a provider."""
        provider = provider or self._active_provider

        if provider not in self._providers:
            raise ValueError(f"Unknown provider: {provider}")

        if provider not in self._clients:
            config = self._providers[provider]
            self._clients[provider] = OpenAI(
                api_key=config.api_key,
                base_url=config.base_url,
            )

        return self._clients[provider], self._providers[provider]

    def model_profile(self, profile_name: str) -> ModelProfile:
        """Get model profile configuration."""
        return _MODEL_PROFILES.get(profile_name, _MODEL_PROFILES["default"])

    def select_task_profile(self, task_type: str) -> str:
        """Select appropriate model profile based on task type."""
        task_lower = task_type.lower()

        # Explicit task-type -> profile mappings
        if task_lower in ("analysis", "review"):
            return "analysis"
        if task_lower == "code":
            return "code_task"
        if task_lower == "consciousness":
            return "consciousness"

        return "default"

    def chat(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        reasoning_effort: str = "medium",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        provider: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Make a chat completion request to LLM.

        Returns: (response_message, usage_dict)
        """
        client, config = self._get_client(provider)

        effort = normalize_reasoning_effort(reasoning_effort)
        profile = self.model_profile("default")

        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": temperature if temperature is not None else profile.temperature,
            "max_tokens": max_tokens if max_tokens is not None else profile.max_tokens,
        }

        # Only add reasoning_effort if provider supports it
        if config.requires_reasoning_effort and effort != "medium":
            kwargs["reasoning_effort"] = {"type": effort}

        if tools:
            kwargs["tools"] = self._format_tools(tools)

        response = client.chat.completions.create(**kwargs)

        msg = response.choices[0].message
        usage = self._extract_usage(response, model)

        return self._message_to_dict(msg), usage

    def vision_query(
        self,
        image_base64: str,
        prompt: str,
        model: str = "glm/glm-4.7",
        max_tokens: int = 1024,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Query a vision model with an image.

        Returns: (text_response, usage_dict)
        """
        client, config = self._get_client(None)

        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}},
            ],
        }]

        # Vision models don't support reasoning_effort
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
        )

        content = response.choices[0].message.content or ""
        usage = self._extract_usage(response, model)

        return content, usage

    # =====================================================================
    # Private Helpers
    # =====================================================================

    def _format_tools(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Format tool schemas for OpenAI-style API."""
        formatted = []
        for tool in tools:
            formatted.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("parameters", {}),
                },
            })
        return formatted

    def _message_to_dict(self, msg: Any) -> Dict[str, Any]:
        """Convert OpenAI message object to dict."""
        result = {"content": msg.content}

        if hasattr(msg, "tool_calls") and msg.tool_calls:
            result["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ]

        return result

    def _extract_usage(self, response: Any, model: str) -> Dict[str, Any]:
        """Extract usage information from API response."""
        if not hasattr(response, "usage"):
            return {}

        usage_obj = response.usage
        if usage_obj is None:
            return {}

        result = {
            "prompt_tokens": getattr(usage_obj, "prompt_tokens", 0),
            "completion_tokens": getattr(usage_obj, "completion_tokens", 0),
            "total_tokens": getattr(usage_obj, "total_tokens", 0),
        }

        # Handle cached tokens (different providers use different fields)
        for attr in ("cache_read_tokens", "cache_write_tokens", "cached_tokens", "cache_creation_tokens"):
            val = getattr(usage_obj, attr, None)
            if val:
                result["cached_tokens"] = (result.get("cached_tokens", 0) or 0) + val
                break

        # Add pricing info
        pricing = _PRICING_STATIC.get(model)
        if pricing:
            prompt_price, completion_price, _ = pricing
            result["estimated_cost_usd"] = (
                (result["prompt_tokens"] / 1_000_000) * prompt_price +
                (result["completion_tokens"] / 1_000_000) * completion_price
            )

        return result
