"""Turn raw Toggl time entries into a deterministic Slack digest.

Every function here is pure (no network, no filesystem, no clock reads
beyond what is passed in) so it can be unit tested with plain fixture data.

The digest is aggregate-only -- total, per-project, per-tag, and per-day --
with no per-entry rows. It is emitted two ways in one Slack payload:

- ``blocks``: Slack Block Kit (header / context / divider / section) so the
  message renders natively and tidily in the channel.
- ``text``: a complete plain-text mirror of the same data. This is the
  fallback Slack shows in notifications, and -- more importantly for this
  project -- the version an LLM reading the channel can always parse, even
  if block rendering is stripped.

Formatting is deliberately rigid (fixed section order, fixed rounding) so
that week-over-week output stays comparable.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from toggl_track_slack_digest.constants import (
    ANOMALY_LINE_TEMPLATE,
    BULLET_PREFIX,
    DAY_SECTION_LABEL,
    DIGEST_HEADER_TITLE,
    NO_ENTRIES_MESSAGE,
    NO_PROJECT_LABEL,
    NO_TAG_LABEL,
    PROJECT_SECTION_LABEL,
    SLACK_SECTION_TEXT_LIMIT,
    TAG_JOIN_SEPARATOR,
    TAG_SECTION_LABEL,
)
from toggl_track_slack_digest.toggl_client import TogglClient


@dataclass(frozen=True)
class DigestData:
    """Aggregated, render-ready digest figures (all durations in seconds).

    Attributes:
        total_seconds: Sum of all completed entry durations.
        total_entries: Count of completed entries.
        by_project: ``(name, seconds, entry_count)`` per project, sorted by
            seconds descending then name.
        by_tag: ``(tag_group, seconds, entry_count)`` per tag group, same
            ordering. A tag group is an entry's full set of tags, sorted
            and comma-joined (see `_tag_group_label`).
        by_day: ``(iso_date, seconds)`` per calendar day, chronological.
        anomalies: ``(iso_date, seconds)`` for days at or above the anomaly
            threshold, chronological.
    """

    total_seconds: int
    total_entries: int
    by_project: list[tuple[str, int, int]]
    by_tag: list[tuple[str, int, int]]
    by_day: list[tuple[str, int]]
    anomalies: list[tuple[str, int]]


def format_digest(
    entries: list[dict[str, Any]],
    project_lookup: dict[int, str],
    timezone: ZoneInfo,
    digest_period_days: int,
    period_start: datetime,
    period_end: datetime,
    anomaly_threshold_hours: int,
) -> tuple[list[dict[str, Any]], str]:
    """Build the Slack digest as ``(blocks, fallback_text)``.

    Args:
        entries: Raw Toggl time entry dicts.
        project_lookup: Mapping of project id to project name.
        timezone: Timezone used to localize entry start times for per-day
            grouping.
        digest_period_days: Number of days the digest covers; denominator
            for the average-hours/day figures.
        period_start: Start of the reporting window (for the header range).
        period_end: End of the reporting window (for the header range).
        anomaly_threshold_hours: Any day at or above this many hours is
            flagged as a likely forgotten running timer.

    Returns:
        A ``(blocks, text)`` tuple. Running entries (negative ``duration``)
        are silently excluded -- the digest reports completed time only. If
        no completed entries remain, returns a minimal "no entries" message
        in both forms.
    """
    completed, _running = TogglClient.split_completed_and_running(entries)

    if not completed:
        blocks = [
            _header_block(),
            _section_block(NO_ENTRIES_MESSAGE),
        ]
        return blocks, NO_ENTRIES_MESSAGE

    data = _aggregate(completed, project_lookup, timezone, anomaly_threshold_hours)
    blocks = build_blocks(data, digest_period_days, period_start, period_end)
    text = build_fallback_text(data, digest_period_days, period_start, period_end)
    return blocks, text


def build_blocks(
    data: DigestData,
    digest_period_days: int,
    period_start: datetime,
    period_end: datetime,
) -> list[dict[str, Any]]:
    """Render `data` as a Slack Block Kit block list."""
    blocks: list[dict[str, Any]] = [
        _header_block(),
        _context_block(_range_summary(data, period_start, period_end)),
    ]

    if data.anomalies:
        blocks.append(_section_block("\n".join(_anomaly_lines(data))))

    blocks.append(_divider_block())
    blocks.extend(
        _section_blocks(
            PROJECT_SECTION_LABEL, _breakdown_lines(data.by_project, data, digest_period_days)
        )
    )
    blocks.append(_divider_block())
    blocks.extend(
        _section_blocks(TAG_SECTION_LABEL, _breakdown_lines(data.by_tag, data, digest_period_days))
    )
    blocks.append(_divider_block())
    blocks.extend(_section_blocks(DAY_SECTION_LABEL, _day_lines(data)))
    return blocks


def build_fallback_text(
    data: DigestData,
    digest_period_days: int,
    period_start: datetime,
    period_end: datetime,
) -> str:
    """Render `data` as a complete plain-text mirror (no Slack markup)."""
    lines = [
        DIGEST_HEADER_TITLE,
        _range_summary(data, period_start, period_end, plain=True),
    ]
    lines.extend(_anomaly_lines(data))
    lines += ["", "By Project:"]
    lines += _breakdown_lines(data.by_project, data, digest_period_days, plain=True)
    lines += ["", "By Tag:"]
    lines += _breakdown_lines(data.by_tag, data, digest_period_days, plain=True)
    lines += ["", "By Day:"]
    lines += _day_lines(data, plain=True)
    return "\n".join(lines)


def format_hm(seconds: int) -> str:
    """Format a non-negative duration in seconds as ``Xh Ym`` (e.g. ``3h 05m``)."""
    total_minutes = round(seconds / 60)
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours}h {minutes:02d}m"


# --- Aggregation ------------------------------------------------------------


def _aggregate(
    entries: list[dict[str, Any]],
    project_lookup: dict[int, str],
    timezone: ZoneInfo,
    anomaly_threshold_hours: int,
) -> DigestData:
    seconds_by_project: dict[str, int] = defaultdict(int)
    count_by_project: dict[str, int] = defaultdict(int)
    seconds_by_tag: dict[str, int] = defaultdict(int)
    count_by_tag: dict[str, int] = defaultdict(int)
    seconds_by_day: dict[str, int] = defaultdict(int)

    for entry in entries:
        duration = entry["duration"]
        project = _project_name(entry, project_lookup)
        tag_group = _tag_group_label(entry)
        day = _local_date(entry, timezone)

        seconds_by_project[project] += duration
        count_by_project[project] += 1
        seconds_by_tag[tag_group] += duration
        count_by_tag[tag_group] += 1
        seconds_by_day[day] += duration

    threshold_seconds = anomaly_threshold_hours * 3600
    anomalies = [
        (day, seconds)
        for day, seconds in sorted(seconds_by_day.items())
        if seconds >= threshold_seconds
    ]

    return DigestData(
        total_seconds=sum(e["duration"] for e in entries),
        total_entries=len(entries),
        by_project=_sorted_buckets(seconds_by_project, count_by_project),
        by_tag=_sorted_buckets(seconds_by_tag, count_by_tag),
        by_day=sorted(seconds_by_day.items()),
        anomalies=anomalies,
    )


def _sorted_buckets(
    seconds_by_name: dict[str, int], count_by_name: dict[str, int]
) -> list[tuple[str, int, int]]:
    return [
        (name, seconds, count_by_name[name])
        for name, seconds in sorted(seconds_by_name.items(), key=lambda item: (-item[1], item[0]))
    ]


# --- Line rendering (shared by blocks and fallback text) --------------------


def _range_summary(
    data: DigestData, period_start: datetime, period_end: datetime, plain: bool = False
) -> str:
    days = f"{period_start:%b} {period_start.day} – {period_end:%b} {period_end.day}, {period_end.year}"
    total = format_hm(data.total_seconds)
    entries = _entries_label(data.total_entries)
    prefix = "" if plain else "🗓 "
    return f"{prefix}{days} · {total} · {entries}"


def _anomaly_lines(data: DigestData) -> list[str]:
    return [
        ANOMALY_LINE_TEMPLATE.format(date=day, duration=format_hm(seconds))
        for day, seconds in data.anomalies
    ]


def _breakdown_lines(
    buckets: list[tuple[str, int, int]],
    data: DigestData,
    digest_period_days: int,
    plain: bool = False,
) -> list[str]:
    lines = []
    for name, seconds, count in buckets:
        percentage = (seconds / data.total_seconds * 100) if data.total_seconds else 0.0
        avg_hours_per_day = seconds / 3600 / digest_period_days
        stats = (
            f"{format_hm(seconds)} · {percentage:.2f}% · "
            f"{avg_hours_per_day:.2f}h/day · {_entries_label(count)}"
        )
        if plain:
            lines.append(f"- {name}: {stats}")
        else:
            lines.append(f"{BULLET_PREFIX}*{name}* — {stats}")
    return lines


def _day_lines(data: DigestData, plain: bool = False) -> list[str]:
    if plain:
        return [f"- {day}: {format_hm(seconds)}" for day, seconds in data.by_day]
    return [f"{BULLET_PREFIX}*{day}* — {format_hm(seconds)}" for day, seconds in data.by_day]


def _entries_label(count: int) -> str:
    return f"{count} entry" if count == 1 else f"{count} entries"


# --- Block Kit helpers ------------------------------------------------------


def _header_block() -> dict[str, Any]:
    return {
        "type": "header",
        "text": {"type": "plain_text", "text": DIGEST_HEADER_TITLE, "emoji": True},
    }


def _context_block(text: str) -> dict[str, Any]:
    return {"type": "context", "elements": [{"type": "mrkdwn", "text": text}]}


def _section_block(text: str) -> dict[str, Any]:
    return {"type": "section", "text": {"type": "mrkdwn", "text": text}}


def _divider_block() -> dict[str, Any]:
    return {"type": "divider"}


def _section_blocks(label: str, lines: list[str]) -> list[dict[str, Any]]:
    """Pack a bold label plus bullet lines into section blocks.

    Long lists are split across multiple section blocks so no single
    block's text exceeds Slack's per-section character limit; the label
    appears only on the first block.
    """
    blocks: list[dict[str, Any]] = []
    current = f"*{label}*"
    for line in lines:
        candidate = f"{current}\n{line}"
        if len(candidate) > SLACK_SECTION_TEXT_LIMIT:
            blocks.append(_section_block(current))
            current = line
        else:
            current = candidate
    blocks.append(_section_block(current))
    return blocks


# --- Entry field helpers ----------------------------------------------------


def _project_name(entry: dict[str, Any], project_lookup: dict[int, str]) -> str:
    project_id = entry.get("project_id")
    if project_id is None:
        return NO_PROJECT_LABEL
    return project_lookup.get(project_id, NO_PROJECT_LABEL)


def _tag_group_label(entry: dict[str, Any]) -> str:
    """Return the entry's tags, sorted and comma-joined, or "No Tag".

    Used as the per-tag bucket key so entries sharing the exact same set of
    tags -- regardless of the order Toggl returned them in -- roll up into
    the same group.
    """
    tags = entry.get("tags") or []
    return TAG_JOIN_SEPARATOR.join(sorted(tags)) if tags else NO_TAG_LABEL


def _local_date(entry: dict[str, Any], timezone: ZoneInfo) -> str:
    start = datetime.fromisoformat(entry["start"].replace("Z", "+00:00"))
    return start.astimezone(timezone).date().isoformat()
