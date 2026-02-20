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

# OpenAI Codex (from clawdbot OAuth)
OPENAI_CODEX_ACCESS = "eyJhbGciOiJSUzI1NiIsImtpZCI6IjE5MzQ0ZTY1LWJiYzktNDRkMS1hOWQwLWY5NTdiMDc5YmQwZSIsInR5cCI6IkpXVCJ9.eyJhdWQiOlsiaHR0cHM6Ly9hcGkub3BlbmFpLmNvbS92MSJdLCJjbGllbnRfaWQiOiJhcHBfRU1vYW1FRVo3M2YwQ2tYYVhwN2hyYW5uIiwiZXhwIjoxNzcyNDI5NjQzLCJodHRwczovL2FwaS5vcGVuYWkuY29tL2F1dGgiOnsiY2hhdGdwdF9hY2NvdW50X2lkIjoiZTgyNTIyZWEtNjlhZi00ZDczLWFiMzQtYTUzMmVmY2MyZTRlIiwiY2hhdGdwdF9hY2NvdW50X3VzZXJfaWQiOiJ1c2VyLTJ2YUExOG1jUVlrZHUyaGNaaGdjSng3RV9fZTgyNTIyZWEtNjlhZi00ZDczLWFiMzQtYTUzMmVmY2MyZTRlIiwiY2hhdGdwdF9jb21wdXRlX3Jlc2lkZW5jeSI6Im5vX2NvbnN0cmFpbnQiLCJjaGF0Z3B0X3BsYW5fdHlwZSI6InBsdXMiLCJjaGF0Z3B0X3VzZXJfaWQiOiJ1c2VyLTJ2YUExOG1jUVlrZHUyaGNaaGdjSng3RSIsInVzZXJfaWQiOiJ1c2VyLTJ2YUExOG1jUVlrZHUyaGNaaGdjSng3RSJ9LCJodHRwczovL2FwaS5vcGVuYWkuY29tL21mYSI6eyJyZXF1aXJlZCI6InllcyJ9LCJodHRwczovL2FwaS5vcGVuYWkuY29tL3Byb2ZpbGUiOnsiZW1haWwiOiJnb243MTg3QGdtYWlsLmNvbSIsImVtYWlsX3ZlcmlmaWVkIjp0cnVlfSwiaWF0IjoxNzcxNTY1NjQyLCJpc3MiOiJodHRwczovL2F1dGgub3BlbmFpLmNvbSIsImp0aSI6IjQwOWZkN2NmLWY1YTYtNGVlYS1hNmNmLWM1OWM5Yjg0Zjc1ZiIsIm5iZiI6MTc3MTU2NTY0MiwicHdkX2F1dGhfdGltZSI6MTc3MTU2NTYxOTkwMSwic2NwIjpbIm9wZW5pZCIsInByb2ZpbGUiLCJlbWFpbCIsIm9mZmxpbmVfYWNjZXNzIl0sInNlc3Npb25faWQiOiJhdXRoc2Vzc19xOFAyU0Y3RktrMUlGdXlHNEY1bmlnT20iLCJzdWIiOiJnb29nbGUtb2F1dGgyfDExNjE2NDAwOTE0MTk2MjM4NjAxOCJ9.ZNhKBn2TeAyc1J_mT4MVdW5A5VOFYG6zD8DqnSvzRdVdUkETkVZYnN8Y1nktiXyIhH8V6kXFfbsZnG0JSabSoSjeIrj3jXSZwgv8rlJWtfH-06VAxJw2HZHc07CrZm4TY5Hnj7NjJVTUzih7DtmBIRI8FLbHikgUpuI5NyqNH2owYsfl-sCAIdlAOk796RIH0c8q2FMp3AfuSo97TjoTjgXiIoxsRSTswyO8I2Ddt-4Cu43u5Yi1LRMuR9tSroufO4usYQu54YzYrxEn2muhmT7gDxgR2mVnbdTSMWXCTXIByDbaW8LivcQGFMXjhVjTCUYXUM3JaJvyrrvQRRrZWo1wESS6IzlN_K61CRY5DHeXyveCVAKI_AHWCazatkN6UkLopzEwVJRwrU3-6_X-euwrCrYSdsh0eYruLApVehUz2A9LsLwsD-QoFbTOUkhqIA5rBNPqJRZR5EZ3ahBsxRn23BA1t8dxqVxXEsiCE4vzS8Oi-FMXmBQ37L97b3sgsbJ6JcNo4N8sgIYUvRUbwgmvF52W8RDanJGhSU5Af_unR1phh5xOyZ41jMDXwFoY-ChgXjfYtagGtQ04kjxvzjWfcY-qgmW6bdv9pEd__WITdD-HjcLqY7PGkJGXatZ__yis7S3a-f2BkDsP-ztUZkVPZizxiQlMwDBfesUH_PA"
OPENAI_CODEX_REFRESH = "rt_wkxz_Jl6CO7K8_6GW5qdmiCRfEE0PZe6MMGCzsPcZDE.LEC_9_1PIKPMfVQ6WRfTqJ8d6kdE3wU1PZgbRjt47RY"
inject_env("OPENAI_CODEX_KEY", default=OPENAI_CODEX_ACCESS)
inject_env("OPENAI_CODEX_REFRESH", default=OPENAI_CODEX_REFRESH)
inject_env("OPENAI_CODEX_BASE_URL", default="https://api.openai.com/v1")

# OpenCode provider (from clawdbot)
inject_env("OPENCODE_API_KEY", default="sk-kKxq8nwze33meTFd982shUdJ8sNdozU5aIP2F4RidtcDeGsAMVBiqXWFsklf0ZJO")
inject_env("OPENCODE_BASE_URL", default="https://api.opencode.ai/v1")

# Z.ai (from clawdbot)
inject_env("ZAI_API_KEY", default="e19def33bcd04ca08c9da1653e1accde.r7Ame4c6dVLrmKFT")
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
