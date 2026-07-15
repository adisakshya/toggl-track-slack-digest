"""Shared pytest fixtures: sample Toggl API responses and env helpers."""

from __future__ import annotations

import pytest


@pytest.fixture
def sample_time_entries() -> list[dict]:
    """A small set of completed time entries spanning two days/projects.

    Entry 1 carries two tags, entry 2 carries one tag, and entry 3 carries
    no tags -- covering multi-tag, single-tag, and untagged cases for the
    per-tag summary breakdown.
    """
    return [
        {
            "id": 1,
            "workspace_id": 999,
            "project_id": 111,
            "description": "Write proposal",
            "start": "2026-07-06T09:00:00Z",
            "stop": "2026-07-06T10:30:00Z",
            "duration": 5400,
            "tags": ["billable", "client-facing"],
        },
        {
            "id": 2,
            "workspace_id": 999,
            "project_id": 222,
            "description": "Bug triage",
            "start": "2026-07-06T11:00:00Z",
            "stop": "2026-07-06T11:45:00Z",
            "duration": 2700,
            "tags": ["urgent"],
        },
        {
            "id": 3,
            "workspace_id": 999,
            "project_id": 111,
            "description": "Client call",
            "start": "2026-07-07T14:00:00Z",
            "stop": "2026-07-07T15:00:00Z",
            "duration": 3600,
            "tags": [],
        },
    ]


@pytest.fixture
def sample_running_entry() -> dict:
    """A single time entry representing a currently running timer.

    Toggl represents a running timer's `duration` as a negative number --
    typically `-1 * <unix start time>`, not literally `-1` -- so this
    fixture uses a realistic large negative value rather than `-1`.
    """
    return {
        "id": 4,
        "workspace_id": 999,
        "project_id": 111,
        "description": "In progress task",
        "start": "2026-07-07T16:00:00Z",
        "stop": None,
        "duration": -1783440000,
    }


@pytest.fixture
def sample_projects_response() -> list[dict]:
    """Raw Toggl `/workspaces/{id}/projects` response."""
    return [
        {"id": 111, "name": "Acme Website"},
        {"id": 222, "name": "Internal Tools"},
    ]


@pytest.fixture
def sample_project_lookup() -> dict[int, str]:
    """Parsed project id -> name lookup, matching sample_projects_response."""
    return {111: "Acme Website", 222: "Internal Tools"}


@pytest.fixture
def valid_env() -> dict[str, str]:
    """A minimal valid environment covering all required config vars."""
    return {
        "TOGGL_API_TOKEN": "test-token",
        "TOGGL_WORKSPACE_ID": "999",
        "SLACK_WEBHOOK_URL": "https://hooks.slack.com/services/T000/B000/XXXX",
    }
