"""Orchestrates the weekly digest job: fetch -> format -> post.

Intended to run as a one-shot process (locally via `make run`, or in CI via
the weekly GitHub Actions workflow). Exits non-zero on any failure so the
Action run is clearly marked as failed.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timedelta

from toggl_track_slack_digest.config import Config, ConfigError
from toggl_track_slack_digest.formatter import format_digest
from toggl_track_slack_digest.slack_client import SlackClient, SlackPostError
from toggl_track_slack_digest.toggl_client import TogglAPIError, TogglClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def compute_date_range(config: Config, now: datetime | None = None) -> tuple[str, str]:
    """Compute the RFC3339 [start, end] range covered by this digest.

    Args:
        config: Loaded configuration (uses `digest_period_days` and
            `timezone`).
        now: Reference "current" time. Defaults to the current time in
            `config.timezone`. Exposed for testability.

    Returns:
        Tuple of (start_date, end_date) as RFC3339 strings.
    """
    current = now or datetime.now(config.zone_info)
    start = current - timedelta(days=config.digest_period_days)
    return start.isoformat(), current.isoformat()


def run() -> None:
    """Run the full fetch -> format -> post pipeline. Raises on failure."""
    logger.info("Loading configuration")
    config = Config.from_env()

    start_date, end_date = compute_date_range(config)
    logger.info(
        "Fetching Toggl time entries from %s to %s (timezone=%s)",
        start_date,
        end_date,
        config.timezone,
    )

    toggl_client = TogglClient(config.toggl_api_token)
    entries = toggl_client.get_time_entries(start_date, end_date)
    logger.info("Fetched %d time entries", len(entries))

    if config.toggl_project_ids:
        entries = [e for e in entries if e.get("project_id") in config.toggl_project_ids]
        logger.info("Filtered to %d entries matching configured project ids", len(entries))

    logger.info("Fetching project list for workspace %s", config.toggl_workspace_id)
    project_lookup = toggl_client.get_projects(config.toggl_workspace_id)
    logger.info("Fetched %d projects", len(project_lookup))

    logger.info("Formatting digest")
    digest_text = format_digest(entries, project_lookup, config.zone_info)

    logger.info("Posting digest to Slack")
    slack_client = SlackClient(config.slack_webhook_url)
    slack_client.post_message(digest_text)

    logger.info("Digest posted successfully")


def main() -> int:
    """Entry point. Returns a process exit code."""
    try:
        run()
    except ConfigError as exc:
        logger.error("Configuration error: %s", exc)
        return 1
    except TogglAPIError as exc:
        logger.error("Toggl API error: %s", exc)
        return 1
    except SlackPostError as exc:
        logger.error("Slack post error: %s", exc)
        return 1
    except Exception:
        logger.exception("Unexpected error running digest job")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
