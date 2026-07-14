"""Tests for formatter.py. Pure functions, no mocking needed."""

from __future__ import annotations

from zoneinfo import ZoneInfo

from toggl_track_slack_digest.formatter import (
    format_digest,
    format_duration,
    format_summary,
    format_time_entries_table,
)

UTC = ZoneInfo("UTC")


def test_format_duration() -> None:
    assert format_duration(5400) == "1:30"
    assert format_duration(3600) == "1:00"
    assert format_duration(1800) == "0:30"
    assert format_duration(36000) == "10:00"


def test_format_time_entries_table_structure(
    sample_time_entries: list[dict], sample_project_lookup: dict[int, str]
) -> None:
    table = format_time_entries_table(sample_time_entries, sample_project_lookup, UTC)
    lines = table.splitlines()

    assert lines[0] == "| Date | Project | Description | Duration (h:mm) |"
    assert lines[1] == "| --- | --- | --- | --- |"
    assert len(lines) == 2 + len(sample_time_entries)


def test_table_rows_sorted_by_date_then_project(
    sample_time_entries: list[dict], sample_project_lookup: dict[int, str]
) -> None:
    table = format_time_entries_table(sample_time_entries, sample_project_lookup, UTC)
    rows = table.splitlines()[2:]

    assert rows[0].startswith("| 2026-07-06 | Acme Website |")
    assert rows[1].startswith("| 2026-07-06 | Internal Tools |")
    assert rows[2].startswith("| 2026-07-07 | Acme Website |")


def test_table_formats_duration_and_description(
    sample_time_entries: list[dict], sample_project_lookup: dict[int, str]
) -> None:
    table = format_time_entries_table(sample_time_entries, sample_project_lookup, UTC)
    rows = table.splitlines()[2:]

    assert "Write proposal" in rows[0]
    assert "1:30" in rows[0]


def test_table_unknown_project_id_labeled(sample_time_entries: list[dict]) -> None:
    table = format_time_entries_table(sample_time_entries, {}, UTC)
    assert "No Project" in table


def test_table_missing_description_labeled(sample_project_lookup: dict[int, str]) -> None:
    entry = {
        "project_id": 111,
        "description": "",
        "start": "2026-07-06T09:00:00Z",
        "duration": 3600,
    }
    table = format_time_entries_table([entry], sample_project_lookup, UTC)
    assert "(no description)" in table


def test_summary_totals(
    sample_time_entries: list[dict], sample_project_lookup: dict[int, str]
) -> None:
    summary = format_summary(sample_time_entries, sample_project_lookup, UTC)

    # 5400 + 2700 + 3600 = 11700s = 3.25h
    assert "**Total hours:** 3.25h" in summary


def test_summary_per_project_sorted_descending(
    sample_time_entries: list[dict], sample_project_lookup: dict[int, str]
) -> None:
    summary = format_summary(sample_time_entries, sample_project_lookup, UTC)
    lines = summary.splitlines()

    project_section_start = lines.index("**Hours per project:**")
    # Acme Website: 5400 + 3600 = 9000s = 2.50h ; Internal Tools: 2700s = 0.75h
    assert lines[project_section_start + 1] == "- Acme Website: 2.50h"
    assert lines[project_section_start + 2] == "- Internal Tools: 0.75h"


def test_summary_per_day(
    sample_time_entries: list[dict], sample_project_lookup: dict[int, str]
) -> None:
    summary = format_summary(sample_time_entries, sample_project_lookup, UTC)
    lines = summary.splitlines()

    day_section_start = lines.index("**Hours per day:**")
    # 2026-07-06: 5400 + 2700 = 8100s = 2.25h ; 2026-07-07: 3600s = 1.00h
    assert lines[day_section_start + 1] == "- 2026-07-06: 2.25h"
    assert lines[day_section_start + 2] == "- 2026-07-07: 1.00h"


def test_format_digest_empty_entries_returns_clean_message() -> None:
    digest = format_digest([], {}, UTC)
    assert digest == "No time entries logged this period."


def test_format_digest_excludes_running_entry_from_totals(
    sample_time_entries: list[dict],
    sample_running_entry: dict,
    sample_project_lookup: dict[int, str],
) -> None:
    entries = sample_time_entries + [sample_running_entry]
    digest = format_digest(entries, sample_project_lookup, UTC)

    assert "**Total hours:** 3.25h" in digest
    assert "1 timer(s) currently running" in digest
    assert "In progress task" not in digest


def test_format_digest_only_running_entries_shows_message_and_flag(
    sample_running_entry: dict,
) -> None:
    digest = format_digest([sample_running_entry], {}, UTC)

    assert digest.startswith("No time entries logged this period.")
    assert "1 timer(s) currently running" in digest


def test_format_digest_includes_table_and_summary(
    sample_time_entries: list[dict], sample_project_lookup: dict[int, str]
) -> None:
    digest = format_digest(sample_time_entries, sample_project_lookup, UTC)

    assert "| Date | Project | Description | Duration (h:mm) |" in digest
    assert "## Summary" in digest


def test_format_digest_timezone_shifts_date_grouping(sample_project_lookup: dict[int, str]) -> None:
    # 2026-07-06T23:30:00Z is 2026-07-07 in UTC+2.
    entry = {
        "project_id": 111,
        "description": "Late task",
        "start": "2026-07-06T23:30:00Z",
        "duration": 3600,
    }
    digest_utc = format_digest([entry], sample_project_lookup, UTC)
    digest_plus2 = format_digest([entry], sample_project_lookup, ZoneInfo("Etc/GMT-2"))

    assert "2026-07-06" in digest_utc
    assert "2026-07-07" in digest_plus2
