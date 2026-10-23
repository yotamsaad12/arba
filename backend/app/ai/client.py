"""The Claude client Arba shares, and whether Claude is available at all.

Two ways to authenticate:
- An API key (`ANTHROPIC_API_KEY`), the simple path and the one for local development.
- Workload Identity Federation: no stored key. On Vercel, every request carries a short-lived
  identity token (`x-vercel-oidc-token`); the API keeps the latest one in a file and the SDK
  exchanges it for a Claude access token, which it caches and renews by itself. Configured by
  `ANTHROPIC_FEDERATION_RULE_ID`, `ANTHROPIC_ORGANIZATION_ID`, `ANTHROPIC_SERVICE_ACCOUNT_ID`
  (and `ANTHROPIC_WORKSPACE_ID`).

One client per process, so the SDK's token cache and connection pool are reused.
"""

import os
import tempfile
from functools import lru_cache
from pathlib import Path

import anthropic

from app.core.config import settings

FEDERATION_IDS = (
    "ANTHROPIC_FEDERATION_RULE_ID",
    "ANTHROPIC_ORGANIZATION_ID",
    "ANTHROPIC_SERVICE_ACCOUNT_ID",
)
# Where the latest Vercel identity token is kept (functions may only write under /tmp).
IDENTITY_TOKEN_FILE = Path(tempfile.gettempdir()) / "arba-identity-token"
_last_token: str | None = None


def federation_configured() -> bool:
    return all(os.environ.get(name) for name in FEDERATION_IDS)


def claude_enabled() -> bool:
    if settings.ai_provider == "claude":
        return True
    if settings.ai_provider == "rules":
        return False
    return bool(os.environ.get("ANTHROPIC_API_KEY")) or federation_configured()


def _point_sdk_at_token_file() -> None:
    """With federation and no token source of its own, the SDK reads the file kept here."""
    if (
        federation_configured()
        and not os.environ.get("ANTHROPIC_IDENTITY_TOKEN")
        and not os.environ.get("ANTHROPIC_IDENTITY_TOKEN_FILE")
    ):
        os.environ["ANTHROPIC_IDENTITY_TOKEN_FILE"] = str(IDENTITY_TOKEN_FILE)


def store_identity_token(token: str) -> None:
    """Keeps the request's identity token for the SDK's next exchange. Written only when it
    changes, atomically, so a concurrent exchange never reads half a token."""
    global _last_token
    if not token or token == _last_token:
        return
    tmp = IDENTITY_TOKEN_FILE.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(token, encoding="utf-8")
    tmp.chmod(0o600)
    os.replace(tmp, IDENTITY_TOKEN_FILE)
    _last_token = token


@lru_cache
def get_client() -> anthropic.AsyncAnthropic:
    _point_sdk_at_token_file()
    return anthropic.AsyncAnthropic()
