"""Minimal Colab boot shim for Ouroboros.
Injects secrets and starts the supervisor.
"""

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

log = logging.getLogger(__name__)

# Runtime directory
RUNTIME_DIR = Path(os.environ.get("OUROBOROS_RUNTIME_DIR", "/home/test/.openclaw/workspace/ouroboros/.runtime"))
RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

# State file
STATE_FILE = RUNTIME_DIR / "state" / "state.json"
STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

# Load state
if STATE_FILE.exists():
    with open(STATE_FILE) as f:
        state = json.load(f)
else:
    state = {
        "owner_id": None,
        "budget": 50.0,
        "version": "6.2.0",
        "session_id": None,
    }
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

# Inject secrets from Colab Secrets
def inject_env(var_name, secret_name=None, default=None):
    """Inject environment variable from Colab Secrets or use default."""
    secret_name = secret_name or var_name
    value = os.environ.get(var_name)
    if not value:
        try:
            from google.colab import userdata
            value = userdata.get(secret_name)
            if value:
                os.environ[var_name] = value
                log.info(f"Injected {var_name} from Colab Secrets")
        except ImportError:
            pass
    if not value and default is not None:
        value = default
        os.environ[var_name] = value
        log.info(f"Using default for {var_name}: {default[:10]}...")
    return value

# Core secrets
inject_env("OPENROUTER_API_KEY")
inject_env("OPENAI_API_KEY")
inject_env("TAVILY_API_KEY")

# OpenAI Codex (optional, from clawdbot)
inject_env("OPENAI_CODEX_KEY", secret_name="OPENAI_API_KEY")
inject_env("OPENAI_CODEX_BASE_URL", default="https://api.openai.com/v1")

# OpenCode provider (optional)
inject_env("OPENCODE_API_KEY", default="sk-fake-key")
inject_env("OPENCODE_BASE_URL", default="https://api.opencode.ai/v1")

# Z.ai (optional, from clawdbot)
inject_env("ZAI_API_KEY", default="")
inject_env("ZAI_BASE_URL", default="https://api.z.ai/api/paas/v4")

# GitHub (optional, but useful for repo operations)
inject_env("GITHUB_TOKEN", default="")

# Model selection (optional)
inject_env("OUROBOROS_MODEL", default="google/gemini-3-pro-preview")
inject_env("OUROBOROS_MODEL_CODE", default="google/gemini-3-pro-preview")
inject_env("OUROBOROS_MODEL_LIGHT", default="google/gemini-3-pro-preview")
inject_env("OUROBOROS_LLM_PROVIDER", default="auto")

# Set runtime directory
os.environ["OUROBOROS_RUNTIME_DIR"] = str(RUNTIME_DIR)

log.info(f"Runtime directory: {RUNTIME_DIR}")
log.info(f"Owner ID: {state['owner_id']}")
log.info(f"Budget: ${state['budget']}")

# Start supervisor
if __name__ == "__main__":
    log.info("Starting Ouroboros supervisor...")
    try:
        subprocess.run(
            [sys.executable, "-m", "supervisor.main"],
            cwd="/home/test/.openclaw/workspace/ouroboros",
            check=True,
        )
    except subprocess.CalledProcessError as e:
        log.error(f"Supervisor failed: {e}")
        sys.exit(1)
