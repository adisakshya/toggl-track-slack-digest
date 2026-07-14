"""Turn raw Toggl time entries into a deterministic Markdown digest.

Every function in this module is pure (no network, no filesystem, no clock
reads beyond what is passed in) so it can be unit tested with plain fixture
data. Formatting choices here are deliberately rigid -- fixed column order,
fixed rounding, fixed section order -- so that week-over-week output is
byte-for-byte comparable and easy for an LLM to parse and diff.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from toggl_track_slack_digest.toggl_client import TogglClient

_TABLE_HEADER = "| Date | Project | Description | Duration (h:mm) |"
_TABLE_SEPARATOR = "| --- | --- | --- | --- |"
_NO_ENTRIES_MESSAGE = "No time entries logged this period."
_NO_PROJECT_LABEL = "No Project"
_NO_DESCRIPTION_LABEL = "(no description)"


def format_digest(
    entries: list[dict[str, Any]],
    project_lookup: dict[int, str],
    timezone: ZoneInfo,
) -> str:
    """Build the full Markdown digest: table + summary.

    Args:
        entries: Raw Toggl time entry dicts.
        project_lookup: Mapping of project id to project name.
        timezone: Timezone used to localize entry start times for display
            and for grouping into calendar days.

    Returns:
        A Markdown string ready to post to Slack. If `entries` contains no
        completed entries, returns a clean "no entries" message (plus a
        note about any running timers) instead of an empty table.
    """
    completed, running = TogglClient.split_completed_and_running(entries)
    running_count = len(running)

    if not completed:
        message = _NO_ENTRIES_MESSAGE
        if running_count:
            message += f"\n\n_{running_count} timer(s) currently running (excluded from totals)._"
        return message

    table = format_time_entries_table(completed, project_lookup, timezone)
    summary = format_summary(completed, project_lookup, timezone)

    sections = [table, "", summary]
    if running_count:
        sections.append(f"\n_{running_count} timer(s) currently running (excluded from totals)._")
    return "\n".join(sections)


def format_time_entries_table(
    entries: list[dict[str, Any]],
    project_lookup: dict[int, str],
    timezone: ZoneInfo,
) -> str:
    """Render completed time entries as a Markdown pipe table.

    Rows are sorted by date ascending, then by project name ascending, so
    output ordering is deterministic across runs.

    Args:
        entries: Completed (non-running) raw Toggl time entry dicts.
        project_lookup: Mapping of project id to project name.
        timezone: Timezone used to localize entry start times.

    Returns:
        A Markdown table string with header, separator, and one row per
        entry.
    """
    rows = []
    for entry in entries:
        date = _local_date(entry, timezone)
        project = _project_name(entry, project_lookup)
        description = entry.get("description") or _NO_DESCRIPTION_LABEL
        duration = format_duration(entry["duration"])
        rows.append((date, project, description, duration))

    rows.sort(key=lambda row: (row[0], row[1]))

    lines = [_TABLE_HEADER, _TABLE_SEPARATOR]
    lines.extend(
        f"| {date} | {project} | {description} | {duration} |"
        for date, project, description, duration in rows
    )
    return "\n".join(lines)


def format_summary(
    entries: list[dict[str, Any]],
    project_lookup: dict[int, str],
    timezone: ZoneInfo,
) -> str:
    """Render the summary section: total, per-project, and per-day hours.

    Args:
        entries: Completed (non-running) raw Toggl time entry dicts.
        project_lookup: Mapping of project id to project name.
        timezone: Timezone used to localize entry start times.

    Returns:
        A Markdown string with a "## Summary" heading followed by total
        hours, hours per project (descending), and hours per day
        (chronological).
    """
    total_seconds = sum(entry["duration"] for entry in entries)

    seconds_by_project: dict[str, int] = defaultdict(int)
    seconds_by_day: dict[str, int] = defaultdict(int)
    for entry in entries:
        seconds_by_project[_project_name(entry, project_lookup)] += entry["duration"]
        seconds_by_day[_local_date(entry, timezone)] += entry["duration"]

    project_lines = [
        f"- {name}: {_to_hours(seconds)}h"
        for name, seconds in sorted(
            seconds_by_project.items(), key=lambda item: (-item[1], item[0])
        )
    ]
    day_lines = [
        f"- {day}: {_to_hours(seconds)}h" for day, seconds in sorted(seconds_by_day.items())
    ]

    lines = [
        "## Summary",
        "",
        f"**Total hours:** {_to_hours(total_seconds)}h",
        "",
        "**Hours per project:**",
        *project_lines,
        "",
        "**Hours per day:**",
        *day_lines,
    ]
    return "\n".join(lines)


def format_duration(seconds: int) -> str:
    """Format a duration in seconds as `H:MM`.

    Args:
        seconds: Duration in seconds. Must not be the running-timer
            sentinel (-1) -- callers must filter those out first.

    Returns:
        A string like `"1:05"` or `"10:00"`.
    """
    total_minutes = round(seconds / 60)
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours}:{minutes:02d}"


def _to_hours(seconds: int) -> str:
    """Format a duration in seconds as decimal hours to 2 places."""
    return f"{seconds / 3600:.2f}"


def _project_name(entry: dict[str, Any], project_lookup: dict[int, str]) -> str:
    project_id = entry.get("project_id")
    if project_id is None:
        return _NO_PROJECT_LABEL
    return project_lookup.get(project_id, _NO_PROJECT_LABEL)


def _local_date(entry: dict[str, Any], timezone: ZoneInfo) -> str:
    start = datetime.fromisoformat(entry["start"].replace("Z", "+00:00"))
    return start.astimezone(timezone).date().isoformat()
