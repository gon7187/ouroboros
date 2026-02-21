"""Supervisor main entrypoint.

Runs Telegram polling loop, worker lifecycle, queue maintenance,
and worker event dispatch.
"""

from __future__ import annotations

import argparse
import datetime
import logging
import os
import pathlib
import queue as pyqueue
import signal
import threading
import time
import traceback
import urllib.parse
import uuid
from collections import deque
from dataclasses import dataclass
from typing import Any, Dict, Optional

from supervisor import events, git_ops, queue, state, telegram, workers


LOG = logging.getLogger(__name__)


@dataclass
class AppConfig:
    repo_dir: pathlib.Path
    drive_root: pathlib.Path
    telegram_token: str
    total_budget: float
    max_workers: int
    soft_timeout_sec: int
    hard_timeout_sec: int
    branch_dev: str
    branch_stable: str
    budget_report_every_messages: int
    poll_timeout_sec: int
    loop_sleep_sec: float
    heartbeat_every_sec: int
    skip_bootstrap_reset: bool
    disable_auto_rescue: bool
    remote_url: str


def _env_bool(name: str, default: bool = False) -> bool:
    raw = str(os.environ.get(name, "1" if default else "0")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def load_config() -> AppConfig:
    cwd = pathlib.Path.cwd()
    repo_dir = pathlib.Path(os.environ.get("OUROBOROS_REPO_DIR", str(cwd))).resolve()
    drive_root = pathlib.Path(os.environ.get("OUROBOROS_DATA_DIR", str(cwd / ".runtime"))).resolve()

    token = str(os.environ.get("TELEGRAM_BOT_TOKEN", "")).strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required")

    total_budget = float(os.environ.get("TOTAL_BUDGET", "50"))
    max_workers = int(os.environ.get("OUROBOROS_MAX_WORKERS", "2"))
    soft_timeout = int(os.environ.get("OUROBOROS_SOFT_TIMEOUT_SEC", "600"))
    hard_timeout = int(os.environ.get("OUROBOROS_HARD_TIMEOUT_SEC", "1800"))

    branch_dev = str(os.environ.get("OUROBOROS_BRANCH_DEV", "ouroboros")).strip() or "ouroboros"
    branch_stable = str(os.environ.get("OUROBOROS_BRANCH_STABLE", "ouroboros-stable")).strip() or "ouroboros-stable"

    gh_user = str(os.environ.get("GITHUB_USER", "")).strip()
    gh_repo = str(os.environ.get("GITHUB_REPO", "")).strip()
    gh_token = str(os.environ.get("GITHUB_TOKEN", "")).strip()
    remote_url = ""
    if gh_user and gh_repo and gh_token:
        token_q = urllib.parse.quote(gh_token, safe="")
        remote_url = f"https://{token_q}@github.com/{gh_user}/{gh_repo}.git"

    return AppConfig(
        repo_dir=repo_dir,
        drive_root=drive_root,
        telegram_token=token,
        total_budget=total_budget,
        max_workers=max_workers,
        soft_timeout_sec=soft_timeout,
        hard_timeout_sec=hard_timeout,
        branch_dev=branch_dev,
        branch_stable=branch_stable,
        budget_report_every_messages=int(os.environ.get("OUROBOROS_BUDGET_REPORT_EVERY_MESSAGES", "10")),
        poll_timeout_sec=int(os.environ.get("OUROBOROS_TG_POLL_TIMEOUT_SEC", "15")),
        loop_sleep_sec=float(os.environ.get("OUROBOROS_LOOP_SLEEP_SEC", "0.2")),
        heartbeat_every_sec=int(os.environ.get("OUROBOROS_MAIN_HEARTBEAT_SEC", "60")),
        skip_bootstrap_reset=_env_bool("OUROBOROS_SKIP_BOOTSTRAP_RESET", True),
        disable_auto_rescue=_env_bool("OUROBOROS_DISABLE_AUTO_RESCUE", False),
        remote_url=remote_url,
    )


def setup_logging() -> None:
    logging.basicConfig(
        level=os.environ.get("OUROBOROS_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


class ConsciousnessController:
    """Thread-safe controller for background consciousness."""

    def __init__(self, instance: Any):
        self._instance = instance
        self._thread: Optional[threading.Thread] = None

    @property
    def is_running(self) -> bool:
        return bool(getattr(self._instance, "_running", False))

    def start(self, interval_sec: int = 300) -> str:
        if self.is_running:
            return "Background consciousness already running"

        def _run() -> None:
            try:
                self._instance.start(interval_sec=interval_sec)
            except Exception:
                LOG.warning("Consciousness thread crashed", exc_info=True)

        self._thread = threading.Thread(target=_run, name="consciousness", daemon=True)
        self._thread.start()
        return "Background consciousness started"

    def stop(self) -> str:
        if not self.is_running:
            return "Background consciousness already stopped"
        try:
            self._instance.stop()
            return "Background consciousness stopped"
        except Exception:
            LOG.warning("Consciousness stop failed", exc_info=True)
            return "Background consciousness stop failed"


class SupervisorContext:
    """Adapter object expected by supervisor.events.dispatch_event."""

    def __init__(self, cfg: AppConfig, tg: telegram.TelegramClient, consciousness: ConsciousnessController):
        self.REPO_DIR = cfg.repo_dir
        self.DRIVE_ROOT = cfg.drive_root
        self.BRANCH_DEV = cfg.branch_dev
        self.BRANCH_STABLE = cfg.branch_stable
        self.TG = tg
        self.consciousness = consciousness

        self.PENDING = queue.PENDING
        self.RUNNING = workers.RUNNING
        self.WORKERS = workers.WORKERS

        self.append_jsonl = state.append_jsonl
        self.load_state = state.load_state
        self.save_state = state.save_state
        self.update_budget_from_usage = state.update_budget_from_usage

        self.send_with_budget = telegram.send_with_budget
        self.queue_review_task = queue.queue_review_task
        self.cancel_task_by_id = queue.cancel_task_by_id
        self.enqueue_task = queue.enqueue_task
        self.sort_pending = queue.sort_pending
        self.persist_queue_snapshot = queue.persist_queue_snapshot

        self.safe_restart = git_ops.safe_restart
        self.kill_workers = workers.kill_workers


def _runtime_dirs(root: pathlib.Path) -> None:
    for rel in ["logs", "state", "locks", "memory", "task_results", "tmp"]:
        (root / rel).mkdir(parents=True, exist_ok=True)


def _set_owner_if_needed(from_id: int, chat_id: int) -> bool:
    st = state.load_state()
    changed = False
    if not st.get("owner_id"):
        st["owner_id"] = int(from_id)
        changed = True
    if not st.get("owner_chat_id"):
        st["owner_chat_id"] = int(chat_id)
        changed = True
    if changed:
        state.save_state(st)
    return changed


def _is_owner(from_id: int) -> bool:
    st = state.load_state()
    owner_id = st.get("owner_id")
    return bool(owner_id) and int(owner_id) == int(from_id)


def _handle_command(text: str, chat_id: int) -> bool:
    cmd = text.strip()
    if not cmd.startswith("/"):
        return False

    if cmd.startswith("/status"):
        msg = state.status_text(workers.WORKERS, queue.PENDING, workers.RUNNING, queue.SOFT_TIMEOUT_SEC, queue.HARD_TIMEOUT_SEC)
        telegram.send_with_budget(chat_id, msg)
        return True

    if cmd.startswith("/queue"):
        telegram.send_with_budget(chat_id, f"Pending: {len(queue.PENDING)} | Running: {len(workers.RUNNING)}")
        return True

    if cmd.startswith("/cancel"):
        parts = cmd.split(maxsplit=1)
        if len(parts) < 2:
            telegram.send_with_budget(chat_id, "Usage: /cancel <task_id>")
            return True
        ok = queue.cancel_task_by_id(parts[1].strip())
        telegram.send_with_budget(chat_id, f"{'OK' if ok else 'Not found'}: {parts[1].strip()}")
        return True

    if cmd.startswith("/evolve"):
        arg = cmd.split(maxsplit=1)[1].strip().lower() if len(cmd.split(maxsplit=1)) > 1 else ""
        st = state.load_state()
        if arg in {"start", "on", "1"}:
            st["evolution_mode_enabled"] = True
            state.save_state(st)
            telegram.send_with_budget(chat_id, "Evolution ON")
        elif arg in {"stop", "off", "0"}:
            st["evolution_mode_enabled"] = False
            state.save_state(st)
            queue.PENDING[:] = [t for t in queue.PENDING if str(t.get("type")) != "evolution"]
            queue.sort_pending()
            queue.persist_queue_snapshot(reason="evolve_off_cmd")
            telegram.send_with_budget(chat_id, "Evolution OFF")
        else:
            telegram.send_with_budget(chat_id, "Usage: /evolve start|stop")
        return True

    if cmd.startswith("/help") or cmd.startswith("/start"):
        telegram.send_with_budget(chat_id, "Commands: /status /queue /cancel <task_id> /evolve start|stop")
        return True

    return False


def _extract_image_data(msg: Dict[str, Any], tg: telegram.TelegramClient) -> Optional[tuple[str, str, str]]:
    photos = msg.get("photo") or []
    if not photos:
        return None
    file_id = photos[-1].get("file_id")
    if not file_id:
        return None
    b64, mime = tg.download_file_base64(file_id)
    if not b64:
        return None
    caption = str(msg.get("caption") or "")
    return b64, mime, caption


def _dispatch_owner_message(chat_id: int, text: str, image_data: Optional[tuple[str, str, str]]) -> None:
    task_id = uuid.uuid4().hex[:8]
    workers.get_event_q().put(
        {
            "type": "owner_message_injected",
            "task_id": task_id,
            "text": text[:200],
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
    )

    th = threading.Thread(
        target=workers.handle_chat_direct,
        args=(chat_id, text, image_data, task_id),
        daemon=True,
        name=f"chat-{task_id}",
    )
    th.start()


def _process_telegram_update(upd: Dict[str, Any], tg: telegram.TelegramClient) -> None:
    msg = upd.get("message") or upd.get("edited_message")
    if not isinstance(msg, dict):
        return

    from_user = msg.get("from") or {}
    from_id = int(from_user.get("id") or 0)
    if not from_id:
        return

    chat = msg.get("chat") or {}
    chat_id = int(chat.get("id") or 0)
    if not chat_id:
        return

    _set_owner_if_needed(from_id, chat_id)
    if not _is_owner(from_id):
        tg.send_message(chat_id, "Not authorized")
        return

    text = str(msg.get("text") or "").strip()
    caption = str(msg.get("caption") or "").strip()
    image_data = _extract_image_data(msg, tg)

    st = state.load_state()
    st["last_owner_message_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    state.save_state(st)

    if text and _handle_command(text, chat_id):
        return

    dispatch_text = text or caption
    if not dispatch_text and image_data:
        dispatch_text = "(image attached)"
    if not dispatch_text:
        return

    _dispatch_owner_message(chat_id, dispatch_text, image_data)


def _drain_worker_events(ctx: SupervisorContext, max_events: int = 200) -> int:
    q = workers.get_event_q()
    handled = 0
    while handled < max_events:
        try:
            evt = q.get_nowait()
        except pyqueue.Empty:
            break
        events.dispatch_event(evt, ctx)
        handled += 1
    return handled


def _acquire_singleton_lock(drive_root: pathlib.Path) -> Optional[tuple[pathlib.Path, int]]:
    """Best-effort singleton lock for supervisor main process."""
    lock_path = drive_root / "locks" / "supervisor_main.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    def _pid_alive(pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except OSError:
            return False

        # Treat non-supervisor or zombie pid as stale lock owner.
        try:
            cmdline_path = pathlib.Path(f"/proc/{pid}/cmdline")
            status_path = pathlib.Path(f"/proc/{pid}/status")
            if not cmdline_path.exists() or not status_path.exists():
                return False
            cmdline = cmdline_path.read_bytes().replace(bytes([0]), b" ").decode("utf-8", "ignore")
            if "supervisor.main" not in cmdline:
                return False
            status_txt = status_path.read_text(encoding="utf-8", errors="ignore")
            if "State:	Z" in status_txt:
                return False
        except Exception:
            # If process metadata can't be read, prefer stale-lock recovery.
            return False

        return True

    # Remove stale lock if owner process is gone
    if lock_path.exists():
        try:
            existing_pid = int(lock_path.read_text(encoding="utf-8").strip() or "0")
        except Exception:
            existing_pid = 0
        if _pid_alive(existing_pid):
            return None
        try:
            lock_path.unlink()
        except Exception:
            return None

    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    fd = os.open(str(lock_path), flags, 0o644)
    os.write(fd, (str(os.getpid()) + "\n").encode("utf-8"))

    os.fsync(fd)
    return lock_path, fd


def _release_singleton_lock(lock_info: Optional[tuple[pathlib.Path, int]]) -> None:
    if not lock_info:
        return
    lock_path, fd = lock_info
    try:
        os.close(fd)
    except Exception:
        pass
    try:
        if lock_path.exists():
            lock_path.unlink()
    except Exception:
        pass


def run() -> None:
    setup_logging()
    cfg = load_config()
    _runtime_dirs(cfg.drive_root)

    lock_info = _acquire_singleton_lock(cfg.drive_root)
    if lock_info is None:
        state.append_jsonl(
            cfg.drive_root / "logs" / "supervisor.jsonl",
            {
                "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "type": "singleton_lock_skip",
                "reason": "another_supervisor_process_running",
            },
        )
        LOG.warning("Another supervisor.main is already running; exiting")
        return

    state.init(cfg.drive_root, cfg.total_budget)
    st = state.init_state()

    tg = telegram.TelegramClient(cfg.telegram_token)
    telegram.init(cfg.drive_root, cfg.total_budget, cfg.budget_report_every_messages, tg)

    git_ops.init(cfg.repo_dir, cfg.drive_root, cfg.remote_url, cfg.branch_dev, cfg.branch_stable)
    workers.init(
        cfg.repo_dir,
        cfg.drive_root,
        cfg.max_workers,
        cfg.soft_timeout_sec,
        cfg.hard_timeout_sec,
        cfg.total_budget,
        cfg.branch_dev,
        cfg.branch_stable,
    )

    consciousness_controller: Optional[ConsciousnessController] = None
    try:
        from ouroboros.consciousness import BackgroundConsciousness

        owner_for_bg = int(st.get("owner_chat_id") or st.get("owner_id") or 0)

        def _emit(event: Dict[str, Any]) -> None:
            if event.get("type") == "owner_message" and owner_for_bg:
                telegram.send_with_budget(owner_for_bg, str(event.get("text") or ""))

        bg = BackgroundConsciousness(
            repo_dir=cfg.repo_dir,
            drive_root=cfg.drive_root,
            owner_id=owner_for_bg,
            emit_fn=_emit,
        )
        consciousness_controller = ConsciousnessController(bg)
    except Exception:
        LOG.warning("Background consciousness unavailable", exc_info=True)

    if consciousness_controller is None:
        class _NoConsciousness:
            is_running = False

            @staticmethod
            def start() -> str:
                return "Background consciousness unavailable"

            @staticmethod
            def stop() -> str:
                return "Background consciousness unavailable"

        consciousness_controller = _NoConsciousness()  # type: ignore[assignment]

    ctx = SupervisorContext(cfg, tg, consciousness_controller)  # type: ignore[arg-type]

    state.append_jsonl(
        cfg.drive_root / "logs" / "supervisor.jsonl",
        {
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "type": "launcher_start",
            "repo_dir": str(cfg.repo_dir),
            "drive_root": str(cfg.drive_root),
            "max_workers": cfg.max_workers,
            "skip_bootstrap_reset": cfg.skip_bootstrap_reset,
        },
    )

    try:
        if cfg.remote_url:
            git_ops.ensure_repo_present()
            if not cfg.skip_bootstrap_reset:
                policy = "ignore" if cfg.disable_auto_rescue else "rescue_and_reset"
                git_ops.checkout_and_reset(cfg.branch_dev, reason="bootstrap", unsynced_policy=policy)
            git_ops.sync_runtime_dependencies(reason="bootstrap")
    except Exception:
        LOG.warning("Repo bootstrap failed", exc_info=True)
        state.append_jsonl(
            cfg.drive_root / "logs" / "supervisor.jsonl",
            {
                "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "type": "bootstrap_error",
                "error": traceback.format_exc()[:3000],
            },
        )

    queue.restore_pending_from_snapshot()
    workers.spawn_workers(cfg.max_workers)
    workers.auto_resume_after_restart()

    stop_flag = {"stop": False}

    def _stop_handler(signum: int, _frame: Any) -> None:
        stop_flag["stop"] = True
        LOG.info("Signal received: %s", signum)

    signal.signal(signal.SIGTERM, _stop_handler)
    signal.signal(signal.SIGINT, _stop_handler)

    offset = int(state.load_state().get("tg_offset") or 0)
    recent_update_ids: set[int] = set()
    recent_update_order: deque[int] = deque(maxlen=4096)
    last_heartbeat = time.time()

    while not stop_flag["stop"]:
        changed_offset = False

        try:
            updates = tg.get_updates(offset=offset, timeout=cfg.poll_timeout_sec)
        except Exception:
            updates = []
            state.append_jsonl(
                cfg.drive_root / "logs" / "supervisor.jsonl",
                {
                    "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "type": "telegram_poll_error",
                    "error": traceback.format_exc()[:2000],
                },
            )

        for upd in updates:
            try:
                update_id = int(upd.get("update_id") or 0)

                # Hard dedup for repeated deliveries in same process
                if update_id and update_id in recent_update_ids:
                    continue

                if update_id >= offset:
                    offset = update_id + 1
                    changed_offset = True

                _process_telegram_update(upd, tg)

                if update_id:
                    recent_update_ids.add(update_id)
                    recent_update_order.append(update_id)
                    while len(recent_update_ids) > 4000 and recent_update_order:
                        old_id = recent_update_order.popleft()
                        recent_update_ids.discard(old_id)
            except Exception:
                state.append_jsonl(
                    cfg.drive_root / "logs" / "supervisor.jsonl",
                    {
                        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        "type": "update_process_error",
                        "error": traceback.format_exc()[:2000],
                    },
                )

        if changed_offset:
            st = state.load_state()
            st["tg_offset"] = offset
            state.save_state(st)

        _drain_worker_events(ctx)
        workers.assign_tasks()
        queue.enforce_task_timeouts()
        workers.ensure_workers_healthy()
        queue.enqueue_evolution_task_if_needed()

        now = time.time()
        if now - last_heartbeat >= cfg.heartbeat_every_sec:
            state.append_jsonl(
                cfg.drive_root / "logs" / "supervisor.jsonl",
                {
                    "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "type": "main_loop_heartbeat",
                    "pending": len(queue.PENDING),
                    "running": len(workers.RUNNING),
                    "workers": len(workers.WORKERS),
                    "offset": offset,
                },
            )
            last_heartbeat = now

        if cfg.loop_sleep_sec > 0:
            time.sleep(cfg.loop_sleep_sec)

    try:
        workers.kill_workers()
    except Exception:
        LOG.warning("Failed to kill workers on shutdown", exc_info=True)

    st = state.load_state()
    st["tg_offset"] = offset
    state.save_state(st)
    queue.persist_queue_snapshot(reason="main_exit")

    state.append_jsonl(
        cfg.drive_root / "logs" / "supervisor.jsonl",
        {
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "type": "main_exit",
        },
    )
    _release_singleton_lock(lock_info)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ouroboros supervisor")
    parser.parse_args()
    run()


if __name__ == "__main__":
    main()