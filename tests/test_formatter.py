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
DIGEST_PERIOD_DAYS = 7


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

    assert lines[0] == "| Date | Project | Tags | Description | Duration (h:mm) |"
    assert lines[1] == "| --- | --- | --- | --- | --- |"
    assert len(lines) == 2 + len(sample_time_entries)


def test_table_rows_sorted_by_date_then_project(
    sample_time_entries: list[dict], sample_project_lookup: dict[int, str]
) -> None:
    table = format_time_entries_table(sample_time_entries, sample_project_lookup, UTC)
    rows = table.splitlines()[2:]

    assert rows[0].startswith("| 2026-07-06 | Acme Website |")
    assert rows[1].startswith("| 2026-07-06 | Internal Tools |")
    assert rows[2].startswith("| 2026-07-07 | Acme Website |")


def test_table_formats_duration_description_and_tags(
    sample_time_entries: list[dict], sample_project_lookup: dict[int, str]
) -> None:
    table = format_time_entries_table(sample_time_entries, sample_project_lookup, UTC)
    rows = table.splitlines()[2:]

    assert "Write proposal" in rows[0]
    assert "1:30" in rows[0]
    assert "billable, client-facing" in rows[0]


def test_table_untagged_entry_shows_no_tag_label(
    sample_time_entries: list[dict], sample_project_lookup: dict[int, str]
) -> None:
    table = format_time_entries_table(sample_time_entries, sample_project_lookup, UTC)
    rows = table.splitlines()[2:]

    assert "| 2026-07-07 | Acme Website | No Tag | Client call | 1:00 |" in rows


def test_table_unknown_project_id_labeled(sample_time_entries: list[dict]) -> None:
    table = format_time_entries_table(sample_time_entries, {}, UTC)
    assert "No Project" in table


def test_table_missing_description_labeled(sample_project_lookup: dict[int, str]) -> None:
    entry = {
        "project_id": 111,
        "description": "",
        "start": "2026-07-06T09:00:00Z",
        "duration": 3600,
        "tags": [],
    }
    table = format_time_entries_table([entry], sample_project_lookup, UTC)
    assert "(no description)" in table


def test_summary_totals(
    sample_time_entries: list[dict], sample_project_lookup: dict[int, str]
) -> None:
    summary = format_summary(sample_time_entries, sample_project_lookup, UTC, DIGEST_PERIOD_DAYS)

    # 5400 + 2700 + 3600 = 11700s = 3.25h
    assert "**Total hours:** 3.25h" in summary


def test_summary_per_project_includes_percentage_and_average(
    sample_time_entries: list[dict], sample_project_lookup: dict[int, str]
) -> None:
    summary = format_summary(sample_time_entries, sample_project_lookup, UTC, DIGEST_PERIOD_DAYS)
    lines = summary.splitlines()

    project_section_start = lines.index("**Hours per project:**")
    # Acme Website: 9000s = 2.50h, 76.92% of 11700s total, avg 2.50/7 = 0.36h/day
    # Internal Tools: 2700s = 0.75h, 23.08% of total, avg 0.75/7 = 0.11h/day
    assert lines[project_section_start + 1] == "- Acme Website: 2.50h (76.92%, avg 0.36h/day)"
    assert lines[project_section_start + 2] == "- Internal Tools: 0.75h (23.08%, avg 0.11h/day)"


def test_summary_per_tag_groups_by_combined_tag_set(
    sample_time_entries: list[dict], sample_project_lookup: dict[int, str]
) -> None:
    summary = format_summary(sample_time_entries, sample_project_lookup, UTC, DIGEST_PERIOD_DAYS)
    lines = summary.splitlines()

    tag_section_start = lines.index("**Hours per tag:**")
    # billable+client-facing (entry1): 5400s = 1.50h
    # No Tag (entry3): 3600s = 1.00h ; urgent (entry2): 2700s = 0.75h
    # Percentages sum to 100% since tag groups partition the entries.
    assert (
        lines[tag_section_start + 1] == "- billable, client-facing: 1.50h (46.15%, avg 0.21h/day)"
    )
    assert lines[tag_section_start + 2] == "- No Tag: 1.00h (30.77%, avg 0.14h/day)"
    assert lines[tag_section_start + 3] == "- urgent: 0.75h (23.08%, avg 0.11h/day)"


def test_summary_per_tag_rolls_up_entries_with_same_tag_set_in_different_order(
    sample_project_lookup: dict[int, str],
) -> None:
    # Two entries carrying the same set of tags, applied in a different
    # order, must land in the same bucket and have their time summed.
    entry_a = {
        "project_id": 111,
        "description": "First",
        "start": "2026-07-06T09:00:00Z",
        "duration": 3600,
        "tags": ["a", "b"],
    }
    entry_b = {
        "project_id": 111,
        "description": "Second",
        "start": "2026-07-06T10:00:00Z",
        "duration": 1800,
        "tags": ["b", "a"],
    }
    summary = format_summary([entry_a, entry_b], sample_project_lookup, UTC, DIGEST_PERIOD_DAYS)
    lines = summary.splitlines()

    tag_section_start = lines.index("**Hours per tag:**")
    assert lines[tag_section_start + 1] == "- a, b: 1.50h (100.00%, avg 0.21h/day)"
    assert lines[tag_section_start + 2] == ""


def test_table_and_summary_sort_tags_alphabetically(
    sample_project_lookup: dict[int, str],
) -> None:
    entry = {
        "project_id": 111,
        "description": "Client delivery work",
        "start": "2026-07-06T09:00:00Z",
        "duration": 3600,
        "tags": ["OLI Delivery", "CSL Behring"],
    }
    digest = format_digest([entry], sample_project_lookup, UTC, DIGEST_PERIOD_DAYS)

    assert "| CSL Behring, OLI Delivery |" in digest
    assert "- CSL Behring, OLI Delivery: 1.00h (100.00%, avg 0.14h/day)" in digest


def test_summary_per_day(
    sample_time_entries: list[dict], sample_project_lookup: dict[int, str]
) -> None:
    summary = format_summary(sample_time_entries, sample_project_lookup, UTC, DIGEST_PERIOD_DAYS)
    lines = summary.splitlines()

    day_section_start = lines.index("**Hours per day:**")
    # 2026-07-06: 5400 + 2700 = 8100s = 2.25h ; 2026-07-07: 3600s = 1.00h
    assert lines[day_section_start + 1] == "- 2026-07-06: 2.25h"
    assert lines[day_section_start + 2] == "- 2026-07-07: 1.00h"


def test_format_digest_empty_entries_returns_clean_message() -> None:
    digest = format_digest([], {}, UTC, DIGEST_PERIOD_DAYS)
    assert digest == "No time entries logged this period."


def test_format_digest_excludes_running_entry_from_totals(
    sample_time_entries: list[dict],
    sample_running_entry: dict,
    sample_project_lookup: dict[int, str],
) -> None:
    entries = sample_time_entries + [sample_running_entry]
    digest = format_digest(entries, sample_project_lookup, UTC, DIGEST_PERIOD_DAYS)

    assert "**Total hours:** 3.25h" in digest
    assert "In progress task" not in digest
    assert "running" not in digest.lower()


def test_format_digest_only_running_entries_returns_clean_message(
    sample_running_entry: dict,
) -> None:
    digest = format_digest([sample_running_entry], {}, UTC, DIGEST_PERIOD_DAYS)

    assert digest == "No time entries logged this period."


def test_format_digest_includes_table_and_summary(
    sample_time_entries: list[dict], sample_project_lookup: dict[int, str]
) -> None:
    digest = format_digest(sample_time_entries, sample_project_lookup, UTC, DIGEST_PERIOD_DAYS)

    assert "| Date | Project | Tags | Description | Duration (h:mm) |" in digest
    assert "## Summary" in digest


def test_format_digest_timezone_shifts_date_grouping(sample_project_lookup: dict[int, str]) -> None:
    # 2026-07-06T23:30:00Z is 2026-07-07 in UTC+2.
    entry = {
        "project_id": 111,
        "description": "Late task",
        "start": "2026-07-06T23:30:00Z",
        "duration": 3600,
        "tags": [],
    }
    digest_utc = format_digest([entry], sample_project_lookup, UTC, DIGEST_PERIOD_DAYS)
    digest_plus2 = format_digest(
        [entry], sample_project_lookup, ZoneInfo("Etc/GMT-2"), DIGEST_PERIOD_DAYS
    )

    assert "2026-07-06" in digest_utc
    assert "2026-07-07" in digest_plus2
