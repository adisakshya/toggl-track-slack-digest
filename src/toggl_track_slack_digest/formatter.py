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

from toggl_track_slack_digest.constants import (
    NO_DESCRIPTION_LABEL,
    NO_ENTRIES_MESSAGE,
    NO_PROJECT_LABEL,
    NO_TAG_LABEL,
    TABLE_HEADER,
    TABLE_SEPARATOR,
    TAG_JOIN_SEPARATOR,
)
from toggl_track_slack_digest.toggl_client import TogglClient


def format_digest(
    entries: list[dict[str, Any]],
    project_lookup: dict[int, str],
    timezone: ZoneInfo,
    digest_period_days: int,
) -> str:
    """Build the full Markdown digest: table + summary.

    Args:
        entries: Raw Toggl time entry dicts.
        project_lookup: Mapping of project id to project name.
        timezone: Timezone used to localize entry start times for display
            and for grouping into calendar days.
        digest_period_days: Number of days the digest covers. Used to
            compute average hours/day per project and per tag in the
            summary.

    Returns:
        A Markdown string ready to post to Slack. If `entries` contains no
        completed entries, returns a clean "no entries" message instead of
        an empty table. Entries for a timer that is still running (a
        negative `duration`) are silently excluded -- this digest only
        reports completed time.
    """
    completed, _running = TogglClient.split_completed_and_running(entries)

    if not completed:
        return NO_ENTRIES_MESSAGE

    table = format_time_entries_table(completed, project_lookup, timezone)
    summary = format_summary(completed, project_lookup, timezone, digest_period_days)
    return "\n".join([table, "", summary])


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
        entry. The Tags column joins all tags on an entry with ", "; an
        entry with no tags shows "No Tag".
    """
    rows = []
    for entry in entries:
        date = _local_date(entry, timezone)
        project = _project_name(entry, project_lookup)
        tags = _tags_cell(entry)
        description = entry.get("description") or NO_DESCRIPTION_LABEL
        duration = format_duration(entry["duration"])
        rows.append((date, project, tags, description, duration))

    rows.sort(key=lambda row: (row[0], row[1]))

    lines = [TABLE_HEADER, TABLE_SEPARATOR]
    lines.extend(
        f"| {date} | {project} | {tags} | {description} | {duration} |"
        for date, project, tags, description, duration in rows
    )
    return "\n".join(lines)


def format_summary(
    entries: list[dict[str, Any]],
    project_lookup: dict[int, str],
    timezone: ZoneInfo,
    digest_period_days: int,
) -> str:
    """Render the summary section: total, per-project, per-tag, per-day.

    Args:
        entries: Completed (non-running) raw Toggl time entry dicts.
        project_lookup: Mapping of project id to project name.
        timezone: Timezone used to localize entry start times.
        digest_period_days: Number of days the digest covers. Used as the
            denominator for the "avg hours/day" figure per project/tag.

    Returns:
        A Markdown string with a "## Summary" heading followed by total
        hours, hours per project (descending, with % of total and average
        hours/day), hours per tag (same shape), and hours per day
        (chronological). A time entry with multiple tags contributes its
        full duration to each of its tags, so per-tag hours/percentages
        need not sum to the total.
    """
    total_seconds = sum(entry["duration"] for entry in entries)

    seconds_by_project: dict[str, int] = defaultdict(int)
    seconds_by_tag: dict[str, int] = defaultdict(int)
    seconds_by_day: dict[str, int] = defaultdict(int)
    for entry in entries:
        seconds_by_project[_project_name(entry, project_lookup)] += entry["duration"]
        seconds_by_day[_local_date(entry, timezone)] += entry["duration"]
        for tag in _tag_names(entry):
            seconds_by_tag[tag] += entry["duration"]

    project_lines = _breakdown_lines(seconds_by_project, total_seconds, digest_period_days)
    tag_lines = _breakdown_lines(seconds_by_tag, total_seconds, digest_period_days)
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
        "**Hours per tag:**",
        *tag_lines,
        "",
        "**Hours per day:**",
        *day_lines,
    ]
    return "\n".join(lines)


def format_duration(seconds: int) -> str:
    """Format a duration in seconds as `H:MM`.

    Args:
        seconds: Duration in seconds. Must not be negative -- negative
            values mark a still-running timer; callers must filter those
            out first.

    Returns:
        A string like `"1:05"` or `"10:00"`.
    """
    total_minutes = round(seconds / 60)
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours}:{minutes:02d}"


def _breakdown_lines(
    seconds_by_bucket: dict[str, int], total_seconds: int, digest_period_days: int
) -> list[str]:
    """Render `- name: Xh (Y%, avg Zh/day)` lines, sorted by hours descending."""
    lines = []
    for name, seconds in sorted(seconds_by_bucket.items(), key=lambda item: (-item[1], item[0])):
        percentage = (seconds / total_seconds * 100) if total_seconds else 0.0
        avg_hours_per_day = seconds / 3600 / digest_period_days
        lines.append(
            f"- {name}: {_to_hours(seconds)}h "
            f"({percentage:.2f}%, avg {avg_hours_per_day:.2f}h/day)"
        )
    return lines


def _to_hours(seconds: int) -> str:
    """Format a duration in seconds as decimal hours to 2 places."""
    return f"{seconds / 3600:.2f}"


def _project_name(entry: dict[str, Any], project_lookup: dict[int, str]) -> str:
    project_id = entry.get("project_id")
    if project_id is None:
        return NO_PROJECT_LABEL
    return project_lookup.get(project_id, NO_PROJECT_LABEL)


def _tag_names(entry: dict[str, Any]) -> list[str]:
    """Return the entry's tag names, or `[NO_TAG_LABEL]` if it has none."""
    tags = entry.get("tags") or []
    return list(tags) if tags else [NO_TAG_LABEL]


def _tags_cell(entry: dict[str, Any]) -> str:
    """Render the table's Tags cell: tags joined with ", ", or "No Tag"."""
    tags = entry.get("tags") or []
    return TAG_JOIN_SEPARATOR.join(tags) if tags else NO_TAG_LABEL


def _local_date(entry: dict[str, Any], timezone: ZoneInfo) -> str:
    start = datetime.fromisoformat(entry["start"].replace("Z", "+00:00"))
    return start.astimezone(timezone).date().isoformat()
