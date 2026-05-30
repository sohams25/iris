"""All adapters expose config.healthcheck() and tolerate missing env."""
from __future__ import annotations
import importlib


def test_slack_config_healthcheck_does_not_raise(monkeypatch):
    for var in ("SLACK_WEBHOOK_URL", "SLACK_BOT_TOKEN", "SLACK_APP_TOKEN", "SLACK_CHANNEL_ID"):
        monkeypatch.delenv(var, raising=False)
    # config.py must import cleanly with no Slack env set (adapter contract)
    # and expose a healthcheck() that returns a well-formed dict.
    mod = importlib.import_module("integrations.slack.config")
    assert hasattr(mod, "healthcheck")
    health = mod.healthcheck()
    assert isinstance(health, dict)
    assert "bot_token_set" in health


def test_discord_stub_healthcheck_reports_not_wired(monkeypatch):
    for v in ("DISCORD_BOT_TOKEN", "DISCORD_CHANNEL_ID"):
        monkeypatch.delenv(v, raising=False)
    mod = importlib.import_module("integrations.discord.config")
    health = mod.healthcheck()
    assert health["wired"] is False
    assert health["token_set"] is False


def test_webhook_stub_healthcheck_reports_not_wired(monkeypatch):
    for v in ("WEBHOOK_URL", "WEBHOOK_SECRET"):
        monkeypatch.delenv(v, raising=False)
    mod = importlib.import_module("integrations.webhook.config")
    health = mod.healthcheck()
    assert health["wired"] is False
