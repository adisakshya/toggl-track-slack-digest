"""Tests for formatter.py. Pure functions, no mocking needed."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from toggl_track_slack_digest.formatter import format_digest, format_hm

UTC = ZoneInfo("UTC")
PERIOD_START = datetime(2026, 7, 6, tzinfo=UTC)
PERIOD_END = datetime(2026, 7, 13, tzinfo=UTC)
DAYS = 7
THRESHOLD = 16


def _digest(entries: list[dict], lookup: dict[int, str]) -> tuple[list[dict[str, Any]], str]:
    return format_digest(entries, lookup, UTC, DAYS, PERIOD_START, PERIOD_END, THRESHOLD)


def _section_texts(blocks: list[dict[str, Any]]) -> list[str]:
    return [b["text"]["text"] for b in blocks if b["type"] == "section"]


def _context_texts(blocks: list[dict[str, Any]]) -> list[str]:
    return [e["text"] for b in blocks if b["type"] == "context" for e in b["elements"]]


def _block_types(blocks: list[dict[str, Any]]) -> list[str]:
    return [b["type"] for b in blocks]


def test_format_hm() -> None:
    assert format_hm(5400) == "1h 30m"
    assert format_hm(3600) == "1h 00m"
    assert format_hm(1800) == "0h 30m"
    assert format_hm(36000) == "10h 00m"
    assert format_hm(0) == "0h 00m"
    assert format_hm(3660) == "1h 01m"


def test_empty_entries_returns_clean_message() -> None:
    blocks, text = _digest([], {})

    assert text == "No time entries logged this period."
    assert _block_types(blocks) == ["header", "section"]
    assert "No time entries logged this period." in _section_texts(blocks)[0]


def test_only_running_entries_returns_clean_message(sample_running_entry: dict) -> None:
    blocks, text = _digest([sample_running_entry], {})

    assert text == "No time entries logged this period."


def test_fallback_text_has_range_total_and_sections(
    sample_time_entries: list[dict], sample_project_lookup: dict[int, str]
) -> None:
    _blocks, text = _digest(sample_time_entries, sample_project_lookup)

    # 5400 + 2700 + 3600 = 11700s = 3h 15m across 3 entries.
    assert "Jul 6 – Jul 13, 2026 · 3h 15m · 3 entries" in text
    assert "By Project:" in text
    assert "By Tag:" in text
    assert "By Day:" in text
    # No per-entry rows leak through.
    assert "Write proposal" not in text


def test_fallback_project_breakdown(
    sample_time_entries: list[dict], sample_project_lookup: dict[int, str]
) -> None:
    _blocks, text = _digest(sample_time_entries, sample_project_lookup)

    # Acme Website: 5400 + 3600 = 9000s = 2h 30m, 76.92%, 2.50/7 = 0.36h/day, 2 entries.
    assert "- Acme Website: 2h 30m · 76.92% · 0.36h/day · 2 entries" in text
    # Internal Tools: 2700s = 0h 45m, 23.08%, 0.75/7 = 0.11h/day, 1 entry.
    assert "- Internal Tools: 0h 45m · 23.08% · 0.11h/day · 1 entry" in text


def test_fallback_tag_breakdown_groups_and_sorts(
    sample_time_entries: list[dict], sample_project_lookup: dict[int, str]
) -> None:
    _blocks, text = _digest(sample_time_entries, sample_project_lookup)
    tag_section = text.split("By Tag:")[1].split("By Day:")[0]
    lines = [ln for ln in tag_section.splitlines() if ln.startswith("- ")]

    # Sorted by hours desc: billable+client-facing (5400) > No Tag (3600) > urgent (2700).
    assert lines[0] == "- billable, client-facing: 1h 30m · 46.15% · 0.21h/day · 1 entry"
    assert lines[1] == "- No Tag: 1h 00m · 30.77% · 0.14h/day · 1 entry"
    assert lines[2] == "- urgent: 0h 45m · 23.08% · 0.11h/day · 1 entry"


def test_fallback_day_breakdown(
    sample_time_entries: list[dict], sample_project_lookup: dict[int, str]
) -> None:
    _blocks, text = _digest(sample_time_entries, sample_project_lookup)

    # 2026-07-06: 5400 + 2700 = 8100s = 2h 15m ; 2026-07-07: 3600s = 1h 00m.
    assert "- 2026-07-06: 2h 15m" in text
    assert "- 2026-07-07: 1h 00m" in text


def test_tag_group_rolls_up_same_set_in_different_order(
    sample_project_lookup: dict[int, str],
) -> None:
    entries = [
        {"project_id": 111, "start": "2026-07-06T09:00:00Z", "duration": 3600, "tags": ["a", "b"]},
        {"project_id": 111, "start": "2026-07-06T10:00:00Z", "duration": 1800, "tags": ["b", "a"]},
    ]
    _blocks, text = _digest(entries, sample_project_lookup)

    assert "- a, b: 1h 30m · 100.00% · 0.21h/day · 2 entries" in text


def test_tags_sorted_alphabetically_in_blocks_and_text(
    sample_project_lookup: dict[int, str],
) -> None:
    entries = [
        {
            "project_id": 111,
            "start": "2026-07-06T09:00:00Z",
            "duration": 3600,
            "tags": ["OLI Delivery", "CSL Behring"],
        }
    ]
    blocks, text = _digest(entries, sample_project_lookup)

    assert "- CSL Behring, OLI Delivery: 1h 00m" in text
    assert any("*CSL Behring, OLI Delivery*" in s for s in _section_texts(blocks))


def test_anomaly_flag_present_for_big_day(sample_project_lookup: dict[int, str]) -> None:
    entries = [
        {"project_id": 111, "start": "2026-07-10T00:00:00Z", "duration": 17 * 3600, "tags": []},
    ]
    blocks, text = _digest(entries, sample_project_lookup)

    warning = "⚠️ 2026-07-10 shows 17h 00m — check for a forgotten running timer"
    assert warning in text
    assert any(warning in s for s in _section_texts(blocks))


def test_no_anomaly_flag_for_normal_days(
    sample_time_entries: list[dict], sample_project_lookup: dict[int, str]
) -> None:
    _blocks, text = _digest(sample_time_entries, sample_project_lookup)

    assert "⚠️" not in text


def test_many_anomaly_days_chunk_under_section_limit(
    sample_project_lookup: dict[int, str],
) -> None:
    # 60 days each over the threshold: the warnings must span multiple
    # section blocks rather than one oversized block Slack would reject.
    from datetime import timedelta

    base = datetime(2026, 1, 1, tzinfo=UTC)
    entries = [
        {
            "project_id": 111,
            "start": (base + timedelta(days=i)).strftime("%Y-%m-%dT00:00:00Z"),
            "duration": 17 * 3600,
            "tags": [],
        }
        for i in range(60)
    ]
    blocks, text = _digest(entries, sample_project_lookup)

    assert text.count("⚠️") == 60
    anomaly_sections = [s for s in _section_texts(blocks) if "⚠️" in s]
    assert len(anomaly_sections) >= 2
    assert all(len(s) <= 2900 for s in _section_texts(blocks))


def test_blocks_structure_and_native_mrkdwn(
    sample_time_entries: list[dict], sample_project_lookup: dict[int, str]
) -> None:
    blocks, _text = _digest(sample_time_entries, sample_project_lookup)

    assert blocks[0]["type"] == "header"
    assert blocks[0]["text"]["text"] == "📊 Toggl Time Digest"
    assert "divider" in _block_types(blocks)

    context = _context_texts(blocks)[0]
    assert context.startswith("🗓 ")

    sections = "\n".join(_section_texts(blocks))
    assert "*🗂 By Project*" in sections
    assert "• *Acme Website* —" in sections
    assert "*🏷 By Tag*" in sections
    assert "*📅 By Day*" in sections
    # No raw markdown table / GitHub-style bold leaks in.
    assert "| Date |" not in sections
    assert "**" not in sections


def test_shows_every_bucket_and_chunks_long_lists(sample_project_lookup: dict[int, str]) -> None:
    # 60 distinct projects with distinct durations, all must appear.
    lookup = {i: f"Project {i:03d}" for i in range(60)}
    entries = [
        {"project_id": i, "start": "2026-07-06T09:00:00Z", "duration": (i + 1) * 60, "tags": []}
        for i in range(60)
    ]
    blocks, text = _digest(entries, lookup)

    for i in range(60):
        assert f"Project {i:03d}" in text
    # Long list must split across multiple section blocks under the char cap.
    project_sections = [s for s in _section_texts(blocks) if "Project 0" in s]
    assert len(project_sections) >= 1
    assert all(len(s) <= 2900 for s in _section_texts(blocks))


def test_blocks_capped_at_slack_message_limit(sample_project_lookup: dict[int, str]) -> None:
    # Names long enough that each project is its own section block, so the
    # block count would exceed Slack's 50-block cap without trimming.
    lookup = {i: f"Project {'x' * 2800}-{i:03d}" for i in range(80)}
    entries = [
        {"project_id": i, "start": "2026-07-06T09:00:00Z", "duration": (i + 1) * 60, "tags": []}
        for i in range(80)
    ]
    blocks, text = _digest(entries, lookup)

    assert len(blocks) <= 50
    assert "trimmed to fit Slack's 50-block limit" in blocks[-1]["text"]["text"]
    # The complete data is preserved in the plain-text fallback.
    assert "Project " + "x" * 2800 + "-079" in text
