"""Claude is available with an API key or with Workload Identity Federation (Vercel)."""

import os
from pathlib import Path

import pytest

from app.ai import client
from app.core.config import settings

IDS = {
    "ANTHROPIC_FEDERATION_RULE_ID": "fdrl_test",
    "ANTHROPIC_ORGANIZATION_ID": "00000000-0000-0000-0000-000000000000",
    "ANTHROPIC_SERVICE_ACCOUNT_ID": "svac_test",
}


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    for name in [
        *IDS,
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_IDENTITY_TOKEN",
        "ANTHROPIC_IDENTITY_TOKEN_FILE",
    ]:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(settings, "ai_provider", "auto")
    token_file = tmp_path / "identity-token"
    monkeypatch.setattr(client, "IDENTITY_TOKEN_FILE", token_file)
    monkeypatch.setattr(client, "_last_token", None)
    client.get_client.cache_clear()
    yield token_file
    client.get_client.cache_clear()


def test_federation_turns_claude_on_and_feeds_the_sdk(
    clean_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert not client.claude_enabled()
    for name, value in IDS.items():
        monkeypatch.setenv(name, value)
    assert client.claude_enabled()

    client.store_identity_token("jwt-1")
    assert clean_env.read_text() == "jwt-1" and oct(clean_env.stat().st_mode)[-3:] == "600"
    client.store_identity_token("jwt-2")
    assert clean_env.read_text() == "jwt-2"

    client.get_client()
    assert os.environ["ANTHROPIC_IDENTITY_TOKEN_FILE"] == str(clean_env)
    # One client per process: the SDK's token cache is shared.
    assert client.get_client() is client.get_client()


def test_api_key_alone_turns_claude_on(clean_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    assert client.claude_enabled()
    monkeypatch.setattr(settings, "ai_provider", "rules")
    assert not client.claude_enabled()
