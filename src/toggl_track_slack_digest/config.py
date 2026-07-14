"""Configuration loading and validation.

All configuration comes exclusively from environment variables. Nothing in
this module (or anywhere else in the project) should hardcode a workspace
id, project id, token, or webhook URL. This makes the digest reusable across
any Toggl workspace / Slack channel by only changing env vars or GitHub
Actions secrets.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_REQUIRED_VARS = ("TOGGL_API_TOKEN", "TOGGL_WORKSPACE_ID", "SLACK_WEBHOOK_URL")


class ConfigError(Exception):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class Config:
    """Fully validated runtime configuration for the digest job.

    Attributes:
        toggl_api_token: Toggl Track API token used for HTTP Basic auth.
        toggl_workspace_id: Toggl workspace id to pull projects from.
        slack_webhook_url: Slack Incoming Webhook URL to post the digest to.
        digest_period_days: Number of trailing days the digest covers.
        toggl_project_ids: Project ids to filter to. Empty tuple means all
            projects are included.
        timezone: IANA timezone name used for date range computation and
            display formatting.
    """

    toggl_api_token: str
    toggl_workspace_id: str
    slack_webhook_url: str
    digest_period_days: int = 7
    toggl_project_ids: tuple[int, ...] = field(default_factory=tuple)
    timezone: str = "UTC"

    @property
    def zone_info(self) -> ZoneInfo:
        """Return the `ZoneInfo` object for `timezone`."""
        return ZoneInfo(self.timezone)

    @classmethod
    def from_env(cls, env: os._Environ[str] | dict[str, str] | None = None) -> "Config":
        """Build a `Config` from environment variables.

        Args:
            env: Mapping to read variables from. Defaults to `os.environ`.
                Exposed as a parameter purely for testability.

        Returns:
            A validated `Config` instance.

        Raises:
            ConfigError: If one or more required variables are missing, or
                an optional variable has an invalid value.
        """
        source = env if env is not None else os.environ

        missing = [name for name in _REQUIRED_VARS if not source.get(name)]
        if missing:
            raise ConfigError(
                "Missing required environment variable(s): "
                f"{', '.join(missing)}. See .env.example for the full list "
                "of supported variables."
            )

        digest_period_days = cls._parse_positive_int(source, "DIGEST_PERIOD_DAYS", default=7)
        toggl_project_ids = cls._parse_project_ids(source)
        timezone = source.get("TIMEZONE", "UTC").strip() or "UTC"
        cls._validate_timezone(timezone)

        return cls(
            toggl_api_token=source["TOGGL_API_TOKEN"],
            toggl_workspace_id=source["TOGGL_WORKSPACE_ID"],
            slack_webhook_url=source["SLACK_WEBHOOK_URL"],
            digest_period_days=digest_period_days,
            toggl_project_ids=toggl_project_ids,
            timezone=timezone,
        )

    @staticmethod
    def _parse_positive_int(
        source: os._Environ[str] | dict[str, str], name: str, default: int
    ) -> int:
        raw = source.get(name)
        if raw is None or raw.strip() == "":
            return default
        try:
            value = int(raw)
        except ValueError as exc:
            raise ConfigError(
                f"Environment variable {name} must be an integer, got: {raw!r}"
            ) from exc
        if value <= 0:
            raise ConfigError(
                f"Environment variable {name} must be a positive integer, got: {value}"
            )
        return value

    @staticmethod
    def _parse_project_ids(source: os._Environ[str] | dict[str, str]) -> tuple[int, ...]:
        raw = source.get("TOGGL_PROJECT_IDS", "")
        if not raw or not raw.strip():
            return ()
        try:
            return tuple(int(part.strip()) for part in raw.split(",") if part.strip())
        except ValueError as exc:
            raise ConfigError(
                "Environment variable TOGGL_PROJECT_IDS must be a comma-separated "
                f"list of integers, got: {raw!r}"
            ) from exc

    @staticmethod
    def _validate_timezone(timezone: str) -> None:
        try:
            ZoneInfo(timezone)
        except ZoneInfoNotFoundError as exc:
            raise ConfigError(
                f"Environment variable TIMEZONE is not a valid IANA timezone: {timezone!r}"
            ) from exc
