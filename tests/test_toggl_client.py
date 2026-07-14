"""Tests for toggl_client.py. All HTTP calls are mocked via `responses`."""

from __future__ import annotations

import responses

from toggl_track_slack_digest.toggl_client import TogglAPIError, TogglClient

_BASE_URL = "https://api.track.toggl.com/api/v9"


@responses.activate
def test_get_time_entries_parses_successful_response(sample_time_entries: list[dict]) -> None:
    responses.add(
        responses.GET,
        f"{_BASE_URL}/me/time_entries",
        json=sample_time_entries,
        status=200,
    )

    client = TogglClient(api_token="test-token")
    entries = client.get_time_entries("2026-07-06T00:00:00Z", "2026-07-13T00:00:00Z")

    assert entries == sample_time_entries


@responses.activate
def test_get_time_entries_handles_empty_response() -> None:
    responses.add(
        responses.GET,
        f"{_BASE_URL}/me/time_entries",
        json=[],
        status=200,
    )

    client = TogglClient(api_token="test-token")
    entries = client.get_time_entries("2026-07-06T00:00:00Z", "2026-07-13T00:00:00Z")

    assert entries == []


@responses.activate
def test_get_time_entries_handles_null_response() -> None:
    responses.add(
        responses.GET,
        f"{_BASE_URL}/me/time_entries",
        body="null",
        content_type="application/json",
        status=200,
    )

    client = TogglClient(api_token="test-token")
    entries = client.get_time_entries("2026-07-06T00:00:00Z", "2026-07-13T00:00:00Z")

    assert entries == []


@responses.activate
def test_get_projects_maps_id_to_name(sample_projects_response: list[dict]) -> None:
    responses.add(
        responses.GET,
        f"{_BASE_URL}/workspaces/999/projects",
        json=sample_projects_response,
        status=200,
    )

    client = TogglClient(api_token="test-token")
    lookup = client.get_projects("999")

    assert lookup == {111: "Acme Website", 222: "Internal Tools"}


@responses.activate
def test_429_triggers_retry_with_backoff(sample_time_entries: list[dict], monkeypatch) -> None:
    sleep_calls: list[float] = []
    monkeypatch.setattr("time.sleep", lambda seconds: sleep_calls.append(seconds))

    responses.add(
        responses.GET,
        f"{_BASE_URL}/me/time_entries",
        status=429,
        headers={"Retry-After": "1"},
    )
    responses.add(
        responses.GET,
        f"{_BASE_URL}/me/time_entries",
        json=sample_time_entries,
        status=200,
    )

    client = TogglClient(api_token="test-token")
    entries = client.get_time_entries("2026-07-06T00:00:00Z", "2026-07-13T00:00:00Z")

    assert entries == sample_time_entries
    assert 1.0 in sleep_calls


@responses.activate
def test_429_exhausts_retries_raises(monkeypatch) -> None:
    monkeypatch.setattr("time.sleep", lambda seconds: None)

    for _ in range(6):
        responses.add(
            responses.GET,
            f"{_BASE_URL}/me/time_entries",
            status=429,
        )

    client = TogglClient(api_token="test-token")
    try:
        client.get_time_entries("2026-07-06T00:00:00Z", "2026-07-13T00:00:00Z")
        assert False, "expected TogglAPIError"
    except TogglAPIError:
        pass


@responses.activate
def test_non_ok_non_429_status_raises() -> None:
    responses.add(
        responses.GET,
        f"{_BASE_URL}/me/time_entries",
        status=500,
        body="internal error",
    )

    client = TogglClient(api_token="test-token")
    try:
        client.get_time_entries("2026-07-06T00:00:00Z", "2026-07-13T00:00:00Z")
        assert False, "expected TogglAPIError"
    except TogglAPIError as exc:
        assert "500" in str(exc)


def test_split_completed_and_running_excludes_running_from_completed(
    sample_time_entries: list[dict], sample_running_entry: dict
) -> None:
    entries = sample_time_entries + [sample_running_entry]

    completed, running = TogglClient.split_completed_and_running(entries)

    assert completed == sample_time_entries
    assert running == [sample_running_entry]
    assert all(entry["duration"] != -1 for entry in completed)
