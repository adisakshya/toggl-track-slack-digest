"""Posts a formatted digest to Slack via an Incoming Webhook.

The digest is sent as a Block Kit message (`blocks`) so it renders
natively in the channel, alongside a plain-text `text` fallback carrying
the same data (shown in notifications, and always parseable by an LLM
reading the channel even if block rendering is stripped). Incoming
Webhooks accept `blocks` with no bot token or OAuth scopes -- only these
non-interactive layout blocks are used, no buttons or menus.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from toggl_track_slack_digest.constants import SLACK_REQUEST_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)


class SlackPostError(Exception):
    """Raised when the Slack webhook rejects or fails to accept a post."""


class SlackClient:
    """Client for posting messages to a Slack Incoming Webhook."""

    def __init__(self, webhook_url: str, session: requests.Session | None = None) -> None:
        """Initialize the client.

        Args:
            webhook_url: Slack Incoming Webhook URL.
            session: Optional pre-built `requests.Session`, primarily for
                dependency injection in tests. A new session is created if
                omitted.
        """
        self._webhook_url = webhook_url
        self._session = session or requests.Session()

    def post_message(self, text: str, blocks: list[dict[str, Any]] | None = None) -> None:
        """Post a message to the configured webhook.

        Args:
            text: Plain-text fallback / notification body. Always sent.
            blocks: Optional Block Kit block list. When provided it is
                included alongside `text` so Slack renders the blocks and
                falls back to `text` where blocks aren't shown.

        Raises:
            SlackPostError: If the request times out, cannot connect, or
                Slack responds with a non-200 status. The response body is
                logged (and included in the exception) to aid debugging,
                since Slack returns human-readable error strings like
                `invalid_payload` or `channel_not_found`.
        """
        payload: dict[str, Any] = {"text": text}
        if blocks is not None:
            payload["blocks"] = blocks
        try:
            response = self._session.post(
                self._webhook_url,
                json=payload,
                timeout=SLACK_REQUEST_TIMEOUT_SECONDS,
            )
        except requests.exceptions.Timeout as exc:
            raise SlackPostError(
                f"Slack webhook request timed out after {SLACK_REQUEST_TIMEOUT_SECONDS}s"
            ) from exc
        except requests.exceptions.RequestException as exc:
            raise SlackPostError(f"Slack webhook request failed: {exc}") from exc

        if response.status_code != 200:
            logger.error(
                "Slack webhook returned non-200 status %d: %s",
                response.status_code,
                response.text,
            )
            raise SlackPostError(f"Slack webhook returned {response.status_code}: {response.text}")

        logger.info("Posted digest to Slack successfully")
