"""Multi-model review tool via LLMClient provider routing."""

import os
import json
import asyncio
import logging

from ouroboros.llm import LLMClient
from ouroboros.utils import utc_now_iso
from ouroboros.tools.registry import ToolEntry, ToolContext

log = logging.getLogger(__name__)
MAX_MODELS = 10
CONCURRENCY_LIMIT = 5


def get_tools():
    return [
        ToolEntry(
            name="multi_model_review",
            schema={
                "name": "multi_model_review",
                "description": "Send content to multiple models for consensus review.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string"},
                        "prompt": {"type": "string"},
                        "models": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["content", "prompt", "models"],
                },
            },
            handler=_handle_multi_model_review,
        )
    ]


def _handle_multi_model_review(ctx: ToolContext, content: str = "", prompt: str = "", models: list = None) -> str:
    if models is None:
        models = []
    try:
        try:
            asyncio.get_running_loop()
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                result = pool.submit(asyncio.run, _multi_model_review_async(content, prompt, models, ctx)).result()
        except RuntimeError:
            result = asyncio.run(_multi_model_review_async(content, prompt, models, ctx))
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        log.error("Multi-model review failed: %s", e, exc_info=True)
        return json.dumps({"error": f"Review failed: {e}"}, ensure_ascii=False)


async def _query_model(llm: LLMClient, model: str, messages: list, semaphore: asyncio.Semaphore):
    async with semaphore:
        try:
            response_msg, usage = await asyncio.to_thread(llm.chat, messages, model, None, "low", 4096, "auto")
            return model, {"message": response_msg, "usage": usage}
        except Exception as e:
            em = str(e)[:300]
            if len(str(e)) > 300:
                em += " [truncated]"
            return model, f"Error: {em}"


def _extract_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for p in content:
            if isinstance(p, dict) and isinstance(p.get("text"), str):
                out.append(p["text"])
            elif isinstance(p, str):
                out.append(p)
        return "\n".join(out).strip()
    return str(content or "")


async def _multi_model_review_async(content: str, prompt: str, models: list, ctx: ToolContext):
    if not content:
        return {"error": "content is required"}
    if not prompt:
        return {"error": "prompt is required"}
    if not models:
        return {"error": "models list is required"}
    if not isinstance(models, list) or not all(isinstance(m, str) and m.strip() for m in models):
        return {"error": "models must be a non-empty list of strings"}
    if len(models) > MAX_MODELS:
        return {"error": f"Too many models requested ({len(models)}). Maximum is {MAX_MODELS}."}

    if not any(str(os.environ.get(k, "")).strip() for k in ("OPENROUTER_API_KEY", "OPENAI_API_KEY", "ZAI_API_KEY")):
        return {"error": "No provider key found. Set OPENROUTER_API_KEY, OPENAI_API_KEY, or ZAI_API_KEY."}

    messages = [{"role": "system", "content": prompt}, {"role": "user", "content": content}]
    llm = LLMClient()
    sem = asyncio.Semaphore(CONCURRENCY_LIMIT)
    results = await asyncio.gather(*[_query_model(llm, m, messages, sem) for m in models])

    review_results = []
    for model, result in results:
        rr = _parse_model_response(model, result)
        _emit_usage_event(rr, ctx)
        review_results.append(rr)

    return {"model_count": len(models), "results": review_results}


def _parse_model_response(model: str, result) -> dict:
    if isinstance(result, str):
        return {"model": model, "verdict": "ERROR", "text": result, "tokens_in": 0, "tokens_out": 0, "cost_estimate": 0.0}

    try:
        msg = result.get("message") or {}
        text = _extract_text(msg.get("content"))
        verdict = "UNKNOWN"
        for line in text.split("\n")[:3]:
            u = line.upper()
            if "PASS" in u:
                verdict = "PASS"; break
            if "FAIL" in u:
                verdict = "FAIL"; break
        if not text:
            text = "(empty model response)"
            verdict = "ERROR"
    except Exception:
        text = "(unexpected response format)"
        verdict = "ERROR"

    usage = (result.get("usage") or {}) if isinstance(result, dict) else {}
    pt = int(usage.get("prompt_tokens") or 0)
    ct = int(usage.get("completion_tokens") or 0)
    try:
        cost = float(usage.get("cost") if usage.get("cost") is not None else (usage.get("total_cost") or 0.0))
    except Exception:
        cost = 0.0

    return {"model": model, "verdict": verdict, "text": text, "tokens_in": pt, "tokens_out": ct, "cost_estimate": cost}


def _emit_usage_event(review_result: dict, ctx: ToolContext) -> None:
    if ctx is None:
        return
    evt = {
        "type": "llm_usage",
        "ts": utc_now_iso(),
        "task_id": ctx.task_id if ctx.task_id else "",
        "model": review_result.get("model", ""),
        "usage": {
            "prompt_tokens": review_result["tokens_in"],
            "completion_tokens": review_result["tokens_out"],
            "cost": review_result["cost_estimate"],
        },
        "category": "review",
    }
    if ctx.event_queue is not None:
        try:
            ctx.event_queue.put_nowait(evt)
            return
        except Exception:
            pass
    if hasattr(ctx, "pending_events"):
        ctx.pending_events.append(evt)
