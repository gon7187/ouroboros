"""
Ouroboros — LLM client.
Supports provider routing for OpenRouter, OpenAI, and z.ai.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

DEFAULT_LIGHT_MODEL = "google/gemini-3-pro-preview"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENAI_BASE_URL = "https://api.openai.com/v1"
ZAI_BASE_URL = "https://api.z.ai/api/paas/v4"


def normalize_reasoning_effort(value: str, default: str = "medium") -> str:
    allowed = {"none", "minimal", "low", "medium", "high", "xhigh"}
    v = str(value or "").strip().lower()
    return v if v in allowed else default


def reasoning_rank(value: str) -> int:
    order = {"none": 0, "minimal": 1, "low": 2, "medium": 3, "high": 4, "xhigh": 5}
    return int(order.get(str(value or "").strip().lower(), 3))


def add_usage(total: Dict[str, Any], usage: Dict[str, Any]) -> None:
    for k in ("prompt_tokens", "completion_tokens", "total_tokens", "cached_tokens", "cache_write_tokens"):
        total[k] = int(total.get(k) or 0) + int(usage.get(k) or 0)
    if usage.get("cost"):
        total["cost"] = float(total.get("cost") or 0) + float(usage["cost"])


def _strip_provider_prefix(model: str) -> str:
    return model.split("/", 1)[1] if "/" in model else model


class LLMClient:
    def __init__(self, api_key: Optional[str] = None, base_url: str = OPENROUTER_BASE_URL):
        self._api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        self._base_url = base_url
        self._clients: Dict[str, Any] = {}

    def _resolve_provider(self, model: str) -> Tuple[str, str, str, str]:
        provider_pref = (os.environ.get("OUROBOROS_LLM_PROVIDER", "auto") or "auto").strip().lower()
        openrouter_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
        zai_key = os.environ.get("ZAI_API_KEY", "").strip()
        openai_base = (os.environ.get("OPENAI_BASE_URL") or OPENAI_BASE_URL).strip()
        zai_base = (os.environ.get("ZAI_BASE_URL") or ZAI_BASE_URL).strip()

        m = (model or "").strip()
        ml = m.lower()

        if provider_pref == "openrouter":
            if not openrouter_key:
                raise ValueError("OPENROUTER_API_KEY not set")
            return "openrouter", m, openrouter_key, OPENROUTER_BASE_URL
        if provider_pref == "openai":
            if not openai_key:
                raise ValueError("OPENAI_API_KEY not set")
            return "openai", _strip_provider_prefix(m) if ml.startswith("openai/") else m, openai_key, openai_base
        if provider_pref == "zai":
            if not zai_key:
                raise ValueError("ZAI_API_KEY not set")
            return "zai", _strip_provider_prefix(m) if ml.startswith(("zai/", "z-ai/")) else m, zai_key, zai_base

        if ml.startswith(("anthropic/", "openai/", "google/", "meta-llama/", "x-ai/", "qwen/", "mistralai/", "deepseek/")) and openrouter_key:
            return "openrouter", m, openrouter_key, OPENROUTER_BASE_URL
        if (ml.startswith(("zai/", "z-ai/", "glm-")) and zai_key):
            return "zai", _strip_provider_prefix(m) if "/" in m else m, zai_key, zai_base
        if (ml.startswith(("openai/", "gpt-", "o1", "o3", "o4")) and openai_key):
            return "openai", _strip_provider_prefix(m) if ml.startswith("openai/") else m, openai_key, openai_base

        if openrouter_key:
            return "openrouter", m, openrouter_key, OPENROUTER_BASE_URL
        if openai_key:
            return "openai", _strip_provider_prefix(m) if ml.startswith("openai/") else m, openai_key, openai_base
        if zai_key:
            return "zai", _strip_provider_prefix(m) if ml.startswith(("zai/", "z-ai/")) else m, zai_key, zai_base

        raise ValueError("No LLM API key configured")

    def _get_client(self, provider: str, base_url: str, api_key: str):
        key = f"{provider}|{base_url}|{api_key[:10]}"
        if key not in self._clients:
            from openai import OpenAI
            self._clients[key] = OpenAI(base_url=base_url, api_key=api_key)
        return self._clients[key]

    def _fetch_generation_cost(self, generation_id: str, api_key: str, base_url: str) -> Optional[float]:
        try:
            import requests
            url = f"{base_url.rstrip('/')}/generation?id={generation_id}"
            resp = requests.get(url, headers={"Authorization": f"Bearer {api_key}"}, timeout=5)
            if resp.status_code == 200:
                data = resp.json().get("data") or {}
                cost = data.get("total_cost") or data.get("usage", {}).get("cost")
                if cost is not None:
                    return float(cost)
            time.sleep(0.5)
            resp = requests.get(url, headers={"Authorization": f"Bearer {api_key}"}, timeout=5)
            if resp.status_code == 200:
                data = resp.json().get("data") or {}
                cost = data.get("total_cost") or data.get("usage", {}).get("cost")
                if cost is not None:
                    return float(cost)
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
        provider, effective_model, api_key, base_url = self._resolve_provider(model)
        client = self._get_client(provider, base_url, api_key)
        effort = normalize_reasoning_effort(reasoning_effort)

        kwargs: Dict[str, Any] = {"model": effective_model, "messages": messages, "max_tokens": max_tokens}
        if provider == "openrouter":
            extra_body: Dict[str, Any] = {"reasoning": {"effort": effort, "exclude": True}}
            if effective_model.startswith("anthropic/"):
                extra_body["provider"] = {"order": ["Anthropic"], "allow_fallbacks": False, "require_parameters": True}
            kwargs["extra_body"] = extra_body

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
        content: List[Dict[str, Any]] = [{"type": "text", "text": prompt}]
        for img in images:
            if "url" in img:
                content.append({"type": "image_url", "image_url": {"url": img["url"]}})
            elif "base64" in img:
                mime = img.get("mime", "image/png")
                content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{img['base64']}"}})

        messages = [{"role": "user", "content": content}]
        response_msg, usage = self.chat(messages=messages, model=model, tools=None, reasoning_effort=reasoning_effort, max_tokens=max_tokens)
        return response_msg.get("content") or "", usage

    def default_model(self) -> str:
        return os.environ.get("OUROBOROS_MODEL", "anthropic/claude-sonnet-4.6")

    def available_models(self) -> List[str]:
        main = os.environ.get("OUROBOROS_MODEL", "anthropic/claude-sonnet-4.6")
        code = os.environ.get("OUROBOROS_MODEL_CODE", "")
        light = os.environ.get("OUROBOROS_MODEL_LIGHT", "")
        models = [main]
        if code and code != main:
            models.append(code)
        if light and light != main and light != code:
            models.append(light)
        return models
