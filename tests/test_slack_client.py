"""Tests for slack_client.py. All HTTP calls are mocked via `responses`."""

from __future__ import annotations

import responses
from responses import matchers

from toggl_track_slack_digest.slack_client import SlackClient, SlackPostError

_WEBHOOK_URL = "https://hooks.slack.com/services/T000/B000/XXXX"


@responses.activate
def test_post_message_success() -> None:
    responses.add(
        responses.POST,
        _WEBHOOK_URL,
        body="ok",
        status=200,
        match=[matchers.json_params_matcher({"text": "hello digest"})],
    )

    client = SlackClient(_WEBHOOK_URL)
    client.post_message("hello digest")  # should not raise


@responses.activate
def test_post_message_includes_blocks_when_provided() -> None:
    blocks = [{"type": "header", "text": {"type": "plain_text", "text": "Digest"}}]
    responses.add(
        responses.POST,
        _WEBHOOK_URL,
        body="ok",
        status=200,
        match=[matchers.json_params_matcher({"text": "fallback", "blocks": blocks})],
    )

    client = SlackClient(_WEBHOOK_URL)
    client.post_message("fallback", blocks=blocks)  # should not raise


@responses.activate
def test_post_message_omits_blocks_when_not_provided() -> None:
    responses.add(
        responses.POST,
        _WEBHOOK_URL,
        body="ok",
        status=200,
        match=[matchers.json_params_matcher({"text": "just text"})],
    )

    client = SlackClient(_WEBHOOK_URL)
    client.post_message("just text")  # should not raise; no blocks key


@responses.activate
def test_post_message_non_200_raises_with_body_in_message() -> None:
    responses.add(
        responses.POST,
        _WEBHOOK_URL,
        body="invalid_payload",
        status=400,
    )

    client = SlackClient(_WEBHOOK_URL)
    try:
        client.post_message("hello digest")
        assert False, "expected SlackPostError"
    except SlackPostError as exc:
        assert "400" in str(exc)
        assert "invalid_payload" in str(exc)


@responses.activate
def test_post_message_timeout_raises() -> None:
    import requests

    responses.add(
        responses.POST,
        _WEBHOOK_URL,
        body=requests.exceptions.Timeout("request timed out"),
    )

    client = SlackClient(_WEBHOOK_URL)
    try:
        client.post_message("hello digest")
        assert False, "expected SlackPostError"
    except SlackPostError as exc:
        assert "timed out" in str(exc)


@responses.activate
def test_post_message_connection_error_raises() -> None:
    import requests

    responses.add(
        responses.POST,
        _WEBHOOK_URL,
        body=requests.exceptions.ConnectionError("connection refused"),
    )

    client = SlackClient(_WEBHOOK_URL)
    try:
        client.post_message("hello digest")
        assert False, "expected SlackPostError"
    except SlackPostError:
        pass
