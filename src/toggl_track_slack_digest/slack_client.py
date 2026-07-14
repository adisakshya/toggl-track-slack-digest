"""Posts a formatted digest to Slack via an Incoming Webhook.

Slack's `mrkdwn` renderer does not turn Markdown pipe tables into visual
tables -- it will display the raw `| a | b |` text. That's fine for this
project: the digest is written to be read programmatically (e.g. by Claude
scanning the channel), not to look pretty to a human. Do not try to convert
the table to Block Kit for visual rendering here; that is out of scope.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT_SECONDS = 10


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

    def post_message(self, text: str) -> None:
        """Post a plain-text (mrkdwn) message to the configured webhook.

        Args:
            text: Message body. Sent as-is inside a single `text` field of
                the webhook payload.

        Raises:
            SlackPostError: If the request times out, cannot connect, or
                Slack responds with a non-200 status. The response body is
                logged (and included in the exception) to aid debugging,
                since Slack returns human-readable error strings like
                `invalid_payload` or `channel_not_found`.
        """
        payload: dict[str, Any] = {"text": text}
        try:
            response = self._session.post(
                self._webhook_url,
                json=payload,
                timeout=_REQUEST_TIMEOUT_SECONDS,
            )
        except requests.exceptions.Timeout as exc:
            raise SlackPostError(
                f"Slack webhook request timed out after {_REQUEST_TIMEOUT_SECONDS}s"
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
