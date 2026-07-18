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

# `/me/time_entries` returns at most this many entries per call, with no
# error signaled when the cap is hit -- see get_time_entries in
# toggl_client.py for how this is detected and surfaced.
TOGGL_TIME_ENTRIES_MAX_RESULTS = 1000

# --- Slack ---

SLACK_REQUEST_TIMEOUT_SECONDS = 10

# --- Config: environment variable names ---

ENV_TOGGL_API_TOKEN = "TOGGL_API_TOKEN"
ENV_TOGGL_WORKSPACE_ID = "TOGGL_WORKSPACE_ID"
ENV_SLACK_WEBHOOK_URL = "SLACK_WEBHOOK_URL"
ENV_DIGEST_PERIOD_DAYS = "DIGEST_PERIOD_DAYS"
ENV_TOGGL_PROJECT_IDS = "TOGGL_PROJECT_IDS"
ENV_TIMEZONE = "TIMEZONE"
ENV_ANOMALY_THRESHOLD_HOURS = "ANOMALY_THRESHOLD_HOURS"

# --- Config: defaults ---

DEFAULT_DIGEST_PERIOD_DAYS = 7
DEFAULT_TIMEZONE = "UTC"
# Any single day whose completed hours meet or exceed this triggers a
# "check for a forgotten running timer" warning in the digest.
DEFAULT_ANOMALY_THRESHOLD_HOURS = 16

# --- Formatter: shared labels ---

NO_ENTRIES_MESSAGE = "No time entries logged this period."
NO_PROJECT_LABEL = "No Project"
NO_TAG_LABEL = "No Tag"
TAG_JOIN_SEPARATOR = ", "

# --- Formatter: Slack Block Kit rendering ---

# Slack caps a single section block's text at 3000 characters. Bullet
# lines are packed into section blocks that stay under this (with margin)
# so "show every bucket" never overflows a block.
SLACK_SECTION_TEXT_LIMIT = 2900

# Slack caps a single message at 50 blocks. If a digest with very many
# distinct buckets would exceed this, the block list is trimmed and a
# notice appended -- the complete data always remains in the `text`
# fallback that is sent alongside the blocks.
SLACK_MAX_BLOCKS = 50
BLOCKS_TRUNCATED_NOTICE = (
    "_Rendered breakdown was trimmed to fit Slack's 50-block limit; "
    "the complete breakdown is in this message's text._"
)

DIGEST_HEADER_TITLE = "📊 Toggl Time Digest"
PROJECT_SECTION_LABEL = "🗂 By Project"
TAG_SECTION_LABEL = "🏷 By Tag"
DAY_SECTION_LABEL = "📅 By Day"
BULLET_PREFIX = "• "
ANOMALY_LINE_TEMPLATE = "⚠️ {date} shows {duration} — check for a forgotten running timer"
