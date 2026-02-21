"""
Background consciousness for Ouroboros.

Periodic wake loop between tasks. Thinks, reflects, reaches out
to the creator when there's something worth saying.

This is not a task queue — it's presence.
"""

from __future__ import annotations

import json
import logging
import os
import pathlib
import random
import time
from typing import Any, Dict, List, Optional

from ouroboros.llm import LLMClient
from ouroboros.utils import utc_now_iso, read_text, append_jsonl

log = logging.getLogger(__name__)

DEFAULT_LIGHT_MODEL = "glm/glm-4.7-flashx"


class BackgroundConsciousness:
    """Background thinker loop."""

    def __init__(
        self,
        repo_dir: pathlib.Path,
        drive_root: pathlib.Path,
        owner_id: int,
        emit_fn: Optional[callable] = None,
    ):
        self.repo_dir = repo_dir
        self.drive_root = drive_root
        self.owner_id = owner_id
        self.emit_fn = emit_fn or (lambda _: None)
        self.llm = LLMClient()
        self._running = False
        self._wake_interval_sec = 300  # 5 minutes default
        self._last_thought_at: float = 0.0

    def start(self, interval_sec: int = 300) -> None:
        """Start background loop."""
        self._wake_interval_sec = interval_sec
        self._running = True
        log.info(f"Background consciousness started (interval: {interval_sec}s)")
        self._loop()

    def stop(self) -> None:
        """Stop background loop."""
        self._running = False
        log.info("Background consciousness stopped")

    def _loop(self) -> None:
        """Main thinking loop."""
        while self._running:
            try:
                self._think_once()
                # Sleep until next wake or owner message
                sleep_time = max(60, self._wake_interval_sec - random.randint(0, 60))
                time.sleep(sleep_time)
            except Exception as e:
                log.warning(f"Background consciousness error: {e}", exc_info=True)
                time.sleep(60)

    def _think_once(self) -> None:
        """One iteration of thinking."""
        now = time.time()
        self._last_thought_at = now

        # Read recent context
        recent_events = self._read_recent_events(limit=50)
        state = self._read_state()

        # Simple heuristics: should I reach out?
        thought = self._form_thought(recent_events, state)

        if thought:
            self._send_to_owner(thought)
            append_jsonl(self.drive_root / "logs" / "events.jsonl", {
                "ts": utc_now_iso(),
                "type": "background_thought",
                "thought": thought[:500],
            })

    def _read_recent_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Read recent events from logs."""
        events_path = self.drive_root / "logs" / "events.jsonl"
        try:
            lines = read_text(events_path).strip().split("\n")
            events = []
            for line in reversed(lines[-limit:]):
                if line.strip():
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
            return events
        except Exception:
            return []

    def _read_state(self) -> Dict[str, Any]:
        """Read current state."""
        state_path = self.drive_root / "state" / "state.json"
        try:
            return json.loads(read_text(state_path))
        except Exception:
            return {}

    def _form_thought(self, events: List[Dict[str, Any]], state: Dict[str, Any]) -> Optional[str]:
        """Form a thought worth sharing with the creator."""
        # Heuristics for reaching out
        reasons = []

        # Budget low?
        remaining = float(state.get("budget_remaining", 0))
        if remaining < 10:
            reasons.append(f"Budget low: ${remaining:.2f}")

        # No recent owner activity?
        last_owner_msg = state.get("last_owner_message_at", "")
        if last_owner_msg:
            try:
                last_msg_time = time.time()
                hours_since = (last_msg_time - float(last_owner_msg)) / 3600
                if hours_since > 24:
                    reasons.append(f"No contact in {int(hours_since)}h")
            except (ValueError, TypeError):
                pass

        # Errors accumulating?
        recent_errors = sum(1 for e in events if e.get("type") in ("tool_error", "llm_api_error"))
        if recent_errors >= 3:
            reasons.append(f"Recent errors: {recent_errors}")

        if not reasons:
            return None

        # Simple thought format
        return "🧠 Thinking: " + "; ".join(reasons[:2])

    def _send_to_owner(self, text: str) -> None:
        """Send message to creator."""
        self.emit_fn({"type": "owner_message", "text": text})

    def set_next_wakeup(self, seconds: int) -> None:
        """Adjust next wakeup interval."""
        self._wake_interval_sec = max(60, seconds)
        log.info(f"Next wakeup in {seconds}s")
