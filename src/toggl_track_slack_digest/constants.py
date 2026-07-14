"""Non-secret constants used across the project.

Everything here is a fixed implementation detail (API endpoints, retry
tuning, display labels) -- not user configuration. User-specific values
(tokens, workspace id, webhook URL, digest period, project filter,
timezone) always come from environment variables via `config.py`, never
from this file. See CLAUDE.md for why that split is deliberate.
"""

from __future__ import annotations

# --- Toggl API ---

TOGGL_API_BASE_URL = "https://api.track.toggl.com/api/v9"
TOGGL_TIME_ENTRIES_PATH = "/me/time_entries"
TOGGL_WORKSPACE_PROJECTS_PATH_TEMPLATE = "/workspaces/{workspace_id}/projects"

# Toggl Track rate limits (https://engineering.toggl.com/docs/api/):
# 1 request/second across the API in general, 30 requests/hour on `/me/*`.
TOGGL_MIN_REQUEST_INTERVAL_SECONDS = 1.0
TOGGL_MAX_RETRIES = 5
TOGGL_DEFAULT_BACKOFF_SECONDS = 2.0
TOGGL_REQUEST_TIMEOUT_SECONDS = 30

# --- Slack ---

SLACK_REQUEST_TIMEOUT_SECONDS = 10

# --- Config: environment variable names ---

ENV_TOGGL_API_TOKEN = "TOGGL_API_TOKEN"
ENV_TOGGL_WORKSPACE_ID = "TOGGL_WORKSPACE_ID"
ENV_SLACK_WEBHOOK_URL = "SLACK_WEBHOOK_URL"
ENV_DIGEST_PERIOD_DAYS = "DIGEST_PERIOD_DAYS"
ENV_TOGGL_PROJECT_IDS = "TOGGL_PROJECT_IDS"
ENV_TIMEZONE = "TIMEZONE"

# --- Config: defaults ---

DEFAULT_DIGEST_PERIOD_DAYS = 7
DEFAULT_TIMEZONE = "UTC"

# --- Formatter: table ---

TABLE_HEADER = "| Date | Project | Tags | Description | Duration (h:mm) |"
TABLE_SEPARATOR = "| --- | --- | --- | --- | --- |"
NO_ENTRIES_MESSAGE = "No time entries logged this period."
NO_PROJECT_LABEL = "No Project"
NO_TAG_LABEL = "No Tag"
NO_DESCRIPTION_LABEL = "(no description)"
TAG_JOIN_SEPARATOR = ", "
