"""Tests for config.py."""

from __future__ import annotations

import pytest

from toggl_track_slack_digest.config import Config, ConfigError


def test_missing_required_var_raises_clear_error(valid_env: dict[str, str]) -> None:
    env = dict(valid_env)
    del env["TOGGL_API_TOKEN"]

    with pytest.raises(ConfigError) as exc_info:
        Config.from_env(env)

    assert "TOGGL_API_TOKEN" in str(exc_info.value)


def test_all_required_vars_missing_lists_all(valid_env: dict[str, str]) -> None:
    with pytest.raises(ConfigError) as exc_info:
        Config.from_env({})

    message = str(exc_info.value)
    assert "TOGGL_API_TOKEN" in message
    assert "TOGGL_WORKSPACE_ID" in message
    assert "SLACK_WEBHOOK_URL" in message


def test_valid_env_loads_correctly(valid_env: dict[str, str]) -> None:
    config = Config.from_env(valid_env)

    assert config.toggl_api_token == "test-token"
    assert config.toggl_workspace_id == "999"
    assert config.slack_webhook_url == "https://hooks.slack.com/services/T000/B000/XXXX"


def test_defaults_apply_when_optional_vars_absent(valid_env: dict[str, str]) -> None:
    config = Config.from_env(valid_env)

    assert config.digest_period_days == 7
    assert config.toggl_project_ids == ()
    assert config.timezone == "UTC"
    assert config.anomaly_threshold_hours == 16


def test_optional_vars_override_defaults(valid_env: dict[str, str]) -> None:
    env = dict(valid_env)
    env["DIGEST_PERIOD_DAYS"] = "14"
    env["TOGGL_PROJECT_IDS"] = "111, 222,333"
    env["TIMEZONE"] = "America/New_York"
    env["ANOMALY_THRESHOLD_HOURS"] = "12"

    config = Config.from_env(env)

    assert config.digest_period_days == 14
    assert config.toggl_project_ids == (111, 222, 333)
    assert config.timezone == "America/New_York"
    assert config.anomaly_threshold_hours == 12


def test_invalid_digest_period_days_raises(valid_env: dict[str, str]) -> None:
    env = dict(valid_env)
    env["DIGEST_PERIOD_DAYS"] = "not-a-number"

    with pytest.raises(ConfigError):
        Config.from_env(env)


def test_invalid_anomaly_threshold_hours_raises(valid_env: dict[str, str]) -> None:
    env = dict(valid_env)
    env["ANOMALY_THRESHOLD_HOURS"] = "0"

    with pytest.raises(ConfigError):
        Config.from_env(env)


def test_invalid_project_ids_raises(valid_env: dict[str, str]) -> None:
    env = dict(valid_env)
    env["TOGGL_PROJECT_IDS"] = "111,abc"

    with pytest.raises(ConfigError):
        Config.from_env(env)


def test_invalid_timezone_raises(valid_env: dict[str, str]) -> None:
    env = dict(valid_env)
    env["TIMEZONE"] = "Not/A_Timezone"

    with pytest.raises(ConfigError):
        Config.from_env(env)
