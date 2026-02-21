"""
Ouroboros — LLM client.

Supports provider routing for OpenRouter, OpenAI, z.ai, OpenCode, and OpenAI Codex.
LLM calls tools directly, no hidden pipelines (Bible P3).
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

# Default models
DEFAULT_LIGHT_MODEL = "google/gemini-3-pro-preview"

# API endpoints
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENAI_BASE_URL = "https://api.openai.com/v1"
OPENAI_CODEX_BASE_URL = "https://api.openai.com/v1"
ZAI_BASE_URL = "https://api.z.ai/api/paas/v4"
OPENCODE_BASE_URL = "https://api.opencode.ai/v1"

# Baseline pricing (per 1M tokens, USD). Updated from OpenRouter API when available.
MODEL_PRICING: Dict[str, Dict[str, float]] = {
    "anthropic/claude-sonnet-4.6": {"prompt": 3.0, "completion": 15.0},
    "anthropic/claude-opus-4.6": {"prompt": 15.0, "completion": 75.0},
    "openai/gpt-4.2": {"prompt": 2.5, "completion": 10.0},
    "google/gemini-2.5-pro-preview": {"prompt": 1.25, "completion": 5.0},
    "openai/gpt-4.1-mini": {"prompt": 0.15, "completion": 0.6},
    "openai/gpt-4.1-turbo": {"prompt": 0.5, "completion": 2.0},
}


def normalize_reasoning_effort(value: str, default: str = "medium") -> str:
    """Normalize reasoning effort to allowed values."""
    allowed = {"none", "minimal", "low", "medium", "high", "xhigh"}
    v = str(value or "").strip().lower()
    return v if v in allowed else default


def reasoning_rank(value: str) -> int:
    """Convert reasoning effort to numeric rank for comparison."""
    order = {"none": 0, "minimal": 1, "low": 2, "medium": 3, "high": 4, "xhigh": 5}
    return int(order.get(str(value or "").strip().lower(), 3))


def add_usage(total: Dict[str, Any], usage: Dict[str, Any]) -> None:
    """Add usage metrics to total."""
    for k in ("prompt_tokens", "completion_tokens", "total_tokens", "cached_tokens", "cache_write_tokens"):
        total[k] = int(total.get(k) or 0) + int(usage.get(k) or 0)
    if usage.get("cost"):
        total["cost"] = float(total.get("cost") or 0) + float(usage["cost"])


def _strip_provider_prefix(model: str) -> str:
    """Remove provider prefix from model name."""
    return model.split("/", 1)[1] if "/" in model else model


class ProviderConfig:
    """Encapsulates provider routing logic."""

    def __init__(self):
        self._env_keys = {
            "openrouter": "OPENROUTER_API_KEY",
            "openai": "OPENAI_API_KEY",
            "openai-codex": "OPENAI_CODEX_KEY",
            "zai": "ZAI_API_KEY",
            "opencode": "OPENCODE_API_KEY",
        }

    def get_key(self, provider: str) -> str:
        """Get API key for provider."""
        return os.environ.get(self._env_keys[provider], "").strip()

    def get_base_url(self, provider: str) -> str:
        """Get base URL for provider."""
        defaults = {
            "openrouter": OPENROUTER_BASE_URL,
            "openai": os.environ.get("OPENAI_BASE_URL", OPENAI_BASE_URL).strip(),
            "openai-codex": os.environ.get("OPENAI_CODEX_BASE_URL", OPENAI_CODEX_BASE_URL).strip(),
            "zai": os.environ.get("ZAI_BASE_URL", ZAI_BASE_URL).strip(),
            "opencode": os.environ.get("OPENCODE_BASE_URL", OPENCODE_BASE_URL).strip(),
        }
        return defaults[provider]

    def resolve_by_model_prefix(self, model: str) -> Optional[Tuple[str, str, str, str]]:
        """Resolve provider by model prefix detection."""
        ml = model.lower()

        # Model prefix → provider mapping
        prefix_map = {
            ("anthropic/", "openai/", "google/", "meta-llama/", "x-ai/", "qwen/", "mistralai/", "deepseek/"): "openrouter",
            ("zai/", "z-ai/", "glm-"): "zai",
            ("opencode/", "open-code/"): "opencode",
            ("openai-codex/", "codex/"): "openai-codex",
            ("openai/", "gpt-", "o1", "o3", "o4"): "openai",
        }

        for prefixes, provider in prefix_map.items():
            if any(ml.startswith(p) for p in prefixes):
                key = self.get_key(provider)
                if not key and provider == "openai-codex":
                    # Fall back to openai key for codex
                    key = self.get_key("openai")
                    provider = "openai"
                if key:
                    base_url = self.get_base_url(provider)
                    effective_model = _strip_provider_prefix(model) if "/" in model else model
                    return provider, effective_model, key, base_url

        return None

    def resolve_by_preference(self, model: str) -> Optional[Tuple[str, str, str, str]]:
        """Resolve provider by explicit environment preference."""
        pref = os.environ.get("OUROBOROS_LLM_PROVIDER", "").strip().lower()

        if not pref or pref == "auto":
            return None

        if pref in self._env_keys:
            key = self.get_key(pref)
            if not key:
                raise ValueError(f"{self._env_keys[pref]} not set")

            base_url = self.get_base_url(pref)
            effective_model = model

            # Strip prefix if needed
            if pref in ("openai", "openai-codex", "zai", "opencode") and "/" in model:
                effective_model = _strip_provider_prefix(model)

            return pref, effective_model, key, base_url

        return None

    def resolve_fallback(self, model: str) -> Tuple[str, str, str, str]:
        """Fallback to first available provider with a key."""
        provider_order = ["openrouter", "openai", "zai", "opencode"]
        ml = model.lower()

        for provider in provider_order:
            key = self.get_key(provider)
            if key:
                base_url = self.get_base_url(provider)
                effective_model = model
                if provider in ("openai", "zai", "opencode") and "/" in model:
                    effective_model = _strip_provider_prefix(model)
                return provider, effective_model, key, base_url

        raise ValueError("No LLM API key configured")

    def resolve(self, model: str) -> Tuple[str, str, str, str]:
        """Resolve provider for a model. Returns (provider, effective_model, key, base_url)."""
        m = (model or "").strip()
        if not m:
            raise ValueError("Model name cannot be empty")

        # 1. Explicit preference
        result = self.resolve_by_preference(m)
        if result:
            return result

        # 2. Model prefix detection
        result = self.resolve_by_model_prefix(m)
        if result:
            return result

        # 3. Special models
        ml = m.lower()
        if ml == "gpt-5.3-codex":
            key = self.get_key("openai-codex") or self.get_key("openai")
            if not key:
                raise ValueError("OPENAI_CODEX_KEY or OPENAI_API_KEY not set for gpt-5.3-codex")
            return "openai", m, key, OPENAI_CODEX_BASE_URL

        # 4. Fallback to first available
        return self.resolve_fallback(m)


class LLMClient:
    """LLM client with multi-provider support."""

    def __init__(self, api_key: Optional[str] = None, base_url: str = OPENROUTER_BASE_URL):
        self._api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        self._base_url = base_url
        self._clients: Dict[str, Any] = {}
        self._provider_config = ProviderConfig()

    def _get_client(self, provider: str, base_url: str, api_key: str):
        """Get or create OpenAI client for provider."""
        key = f"{provider}|{base_url}|{api_key[:10]}"
        if key not in self._clients:
            from openai import OpenAI
            self._clients[key] = OpenAI(base_url=base_url, api_key=api_key)
        return self._clients[key]

    def _fetch_generation_cost(self, generation_id: str, api_key: str, base_url: str) -> Optional[float]:
        """Fetch cost from OpenRouter for a generation."""
        try:
            import requests
            url = f"{base_url.rstrip('/')}/generation?id={generation_id}"
            for _ in range(2):
                resp = requests.get(url, headers={"Authorization": f"Bearer {api_key}"}, timeout=5)
                if resp.status_code == 200:
                    data = resp.json().get("data") or {}
                    cost = data.get("total_cost") or data.get("usage", {}).get("cost")
                    if cost is not None:
                        return float(cost)
                time.sleep(0.5)
        except Exception:
            log.debug("Failed to fetch generation cost", exc_info=True)
        return None

    def chat(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        reasoning_effort: str = "medium",
        max_tokens: int = 16384,
        tool_choice: str = "auto",
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Send chat completion request to LLM."""
        provider, effective_model, api_key, base_url = self._provider_config.resolve(model)
        client = self._get_client(provider, base_url, api_key)
        effort = normalize_reasoning_effort(reasoning_effort)

        kwargs: Dict[str, Any] = {"model": effective_model, "messages": messages, "max_tokens": max_tokens}

        # OpenRouter-specific configuration
        if provider == "openrouter":
            extra_body: Dict[str, Any] = {"reasoning": {"effort": effort, "exclude": True}}
            if effective_model.startswith("anthropic/"):
                extra_body["provider"] = {"order": ["Anthropic"], "allow_fallbacks": False, "require_parameters": True}
            kwargs["extra_body"] = extra_body

        # Tool configuration
        if tools:
            tools_payload = [t for t in tools]
            if provider == "openrouter" and tools_payload:
                last_tool = {**tools_payload[-1]}
                last_tool["cache_control"] = {"type": "ephemeral", "ttl": "1h"}
                tools_payload[-1] = last_tool
            kwargs["tools"] = tools_payload
            kwargs["tool_choice"] = tool_choice

        resp = client.chat.completions.create(**kwargs)
        resp_dict = resp.model_dump()
        usage = resp_dict.get("usage") or {}
        choices = resp_dict.get("choices") or [{}]
        msg = (choices[0] if choices else {}).get("message") or {}

        # Normalize usage fields
        if not usage.get("cached_tokens"):
            d = usage.get("prompt_tokens_details") or {}
            if isinstance(d, dict) and d.get("cached_tokens"):
                usage["cached_tokens"] = int(d["cached_tokens"])

        if not usage.get("cache_write_tokens"):
            d = usage.get("prompt_tokens_details") or {}
            if isinstance(d, dict):
                cw = d.get("cache_write_tokens") or d.get("cache_creation_tokens") or d.get("cache_creation_input_tokens")
                if cw:
                    usage["cache_write_tokens"] = int(cw)

        # Fetch cost from OpenRouter
        if provider == "openrouter" and not usage.get("cost"):
            gen_id = resp_dict.get("id") or ""
            if gen_id:
                c = self._fetch_generation_cost(gen_id, api_key=api_key, base_url=base_url)
                if c is not None:
                    usage["cost"] = c

        return msg, usage

    def vision_query(
        self,
        prompt: str,
        images: List[Dict[str, Any]],
        model: str = "anthropic/claude-sonnet-4.6",
        max_tokens: int = 1024,
        reasoning_effort: str = "low",
    ) -> Tuple[str, Dict[str, Any]]:
        """Send vision query with images."""
        content: List[Dict[str, Any]] = [{"type": "text", "text": prompt}]
        for img in images:
            if "url" in img:
                content.append({"type": "image_url", "image_url": {"url": img["url"]}})
            elif "base64" in img:
                mime = img.get("mime", "image/png")
                content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{img['base64']}"}})

        messages = [{"role": "user", "content": content}]
        response_msg, usage = self.chat(messages=messages, model=model, tools=None, max_tokens=max_tokens)
        return response_msg.get("content") or "", usage


def fetch_openrouter_pricing() -> Dict[str, Dict[str, float]]:
    """Fetch current pricing from OpenRouter API and update MODEL_PRICING."""
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        log.debug("No OpenRouter API key, skipping pricing fetch")
        return MODEL_PRICING.copy()

    try:
        import requests
        url = f"{OPENROUTER_BASE_URL}/models"
        resp = requests.get(url, headers={"Authorization": f"Bearer {api_key}"}, timeout=10)
        if resp.status_code != 200:
            log.warning(f"Failed to fetch OpenRouter pricing: HTTP {resp.status_code}")
            return MODEL_PRICING.copy()

        data = resp.json()
        updated = 0
        for model_data in data.get("data", []):
            model_id = model_data.get("id", "")
            pricing = model_data.get("pricing", {})
            if model_id and isinstance(pricing, dict):
                prompt_price = float(pricing.get("prompt", 0))
                completion_price = float(pricing.get("completion", 0))
                if prompt_price > 0 or completion_price > 0:
                    MODEL_PRICING[model_id] = {"prompt": prompt_price, "completion": completion_price}
                    updated += 1

        log.info(f"Updated pricing for {updated} models from OpenRouter")
    except Exception as e:
        log.warning(f"Failed to fetch OpenRouter pricing: {e}")

    return MODEL_PRICING.copy()
