"""Thin wrapper around the Toggl Track API v9.

Toggl Track rate limits (https://engineering.toggl.com/docs/api/):

- 1 request/second across the API in general.
- 30 requests/hour specifically on the `/me/*` endpoints (which includes
  `get_time_entries`).

This client enforces a minimum spacing between outgoing requests and retries
on HTTP 429 with exponential backoff, honoring the `Retry-After` header when
the server provides one. Since this project runs stateless, one-shot jobs
(a handful of requests per run), the 30/hour `/me/*` ceiling is not tracked
across runs -- it is documented here so callers scheduling this job know not
to invoke it more than a few times per hour against the same token.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.track.toggl.com/api/v9"
_MIN_REQUEST_INTERVAL_SECONDS = 1.0
_MAX_RETRIES = 5
_DEFAULT_BACKOFF_SECONDS = 2.0
_REQUEST_TIMEOUT_SECONDS = 30

#: Toggl marks a time entry whose timer is still running (has a `start` but
#: no `stop` yet) with a negative `duration`. It is not reliably `-1` --
#: commonly it is `-1 * <unix start time>` -- so callers must check
#: `duration < 0`, not equality against a fixed sentinel value.


class TogglAPIError(Exception):
    """Raised when the Toggl API returns an unrecoverable error response."""


class TogglClient:
    """Client for the Toggl Track API v9.

    Attributes:
        api_token: Toggl API token, sent as the HTTP Basic auth username
            with a literal password of `api_token`, per Toggl convention.
    """

    def __init__(self, api_token: str, session: Optional[requests.Session] = None) -> None:
        """Initialize the client.

        Args:
            api_token: Toggl Track API token.
            session: Optional pre-built `requests.Session`, primarily for
                dependency injection in tests. A new session is created if
                omitted.
        """
        self._api_token = api_token
        self._session = session or requests.Session()
        self._last_request_time: Optional[float] = None

    def get_time_entries(self, start_date: str, end_date: str) -> list[dict[str, Any]]:
        """Fetch time entries for the authenticated user in a date range.

        Args:
            start_date: ISO 8601 / RFC3339 start of the range (inclusive).
            end_date: ISO 8601 / RFC3339 end of the range (inclusive).

        Returns:
            A list of raw time entry dicts as returned by the API. Empty
            list if no entries fall in the range. Entries with a negative
            `duration` are included (they represent a timer still running)
            -- callers are responsible for excluding them from
            completed-time totals.
        """
        response = self._request(
            "GET",
            "/me/time_entries",
            params={"start_date": start_date, "end_date": end_date},
        )
        data = response.json()
        return data if data else []

    def get_projects(self, workspace_id: str) -> dict[int, str]:
        """Fetch all projects for a workspace and map id -> name.

        Time entries only carry a `project_id`, not a project name, so this
        lookup is required to render human-readable project names.

        Args:
            workspace_id: Toggl workspace id.

        Returns:
            Mapping of project id to project name. Empty dict if the
            workspace has no projects.
        """
        response = self._request("GET", f"/workspaces/{workspace_id}/projects")
        data = response.json()
        return {project["id"]: project["name"] for project in (data or [])}

    @staticmethod
    def split_completed_and_running(
        entries: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Split time entries into (completed, running).

        Args:
            entries: Raw time entry dicts, as returned by `get_time_entries`.

        Returns:
            A `(completed, running)` tuple. `running` holds entries whose
            timer is still active (negative `duration`); those should be
            excluded from completed-time totals but may be surfaced
            separately (e.g. "N timers currently running").
        """
        completed = [e for e in entries if e.get("duration", 0) >= 0]
        running = [e for e in entries if e.get("duration", 0) < 0]
        return completed, running

    def _request(
        self, method: str, path: str, params: Optional[dict[str, Any]] = None
    ) -> requests.Response:
        url = f"{_BASE_URL}{path}"
        attempt = 0
        while True:
            self._throttle()
            logger.info("Toggl API request: %s %s", method, path)
            response = self._session.request(
                method,
                url,
                params=params,
                auth=(self._api_token, "api_token"),
                timeout=_REQUEST_TIMEOUT_SECONDS,
            )
            self._last_request_time = time.monotonic()

            if response.status_code == 429:
                attempt += 1
                if attempt > _MAX_RETRIES:
                    raise TogglAPIError(
                        f"Toggl API rate limit exceeded after {_MAX_RETRIES} retries "
                        f"for {method} {path}"
                    )
                wait_seconds = self._retry_delay(response, attempt)
                logger.info(
                    "Toggl API rate limited (429) on %s %s, retrying in %.1fs (attempt %d/%d)",
                    method,
                    path,
                    wait_seconds,
                    attempt,
                    _MAX_RETRIES,
                )
                time.sleep(wait_seconds)
                continue

            if not response.ok:
                raise TogglAPIError(
                    f"Toggl API request failed: {method} {path} returned "
                    f"{response.status_code}: {response.text}"
                )

            return response

    def _throttle(self) -> None:
        """Sleep as needed to respect the 1 request/second Toggl API limit."""
        if self._last_request_time is None:
            return
        elapsed = time.monotonic() - self._last_request_time
        remaining = _MIN_REQUEST_INTERVAL_SECONDS - elapsed
        if remaining > 0:
            time.sleep(remaining)

    @staticmethod
    def _retry_delay(response: requests.Response, attempt: int) -> float:
        retry_after: Optional[str] = response.headers.get("Retry-After")
        if retry_after is not None:
            try:
                return float(retry_after)
            except ValueError:
                pass
        return float(_DEFAULT_BACKOFF_SECONDS * (2 ** (attempt - 1)))
