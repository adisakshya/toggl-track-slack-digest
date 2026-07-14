# CLAUDE.md

Guidance for future Claude Code sessions working in this repository.

## Purpose

Fetches the last N days of Toggl Track time entries, formats them as a
Markdown table + summary, and posts the result to Slack via an Incoming
Webhook. Runs as a stateless, one-shot job (locally or on a weekly GitHub
Actions cron).

## Constraints to always respect

- **Never hardcode configuration.** Workspace id, project ids, API token,
  webhook URL, digest period, and timezone all come from environment
  variables only (see `src/toggl_track_slack_digest/config.py`). Don't add
  a YAML/JSON config file, and don't inline a default workspace/project id
  anywhere.
- **Respect Toggl's rate limits.** 1 request/second across the API, 30
  requests/hour on `/me/*` endpoints. `toggl_client.py` already throttles
  and retries on 429 with backoff (honoring `Retry-After`). Don't add new
  Toggl calls without going through `TogglClient._request`, and don't
  increase request frequency without re-checking this limit.
- **Never log secrets.** `TOGGL_API_TOKEN` and `SLACK_WEBHOOK_URL` must
  never appear in log output, print statements, or exceptions. Log request
  paths/status, not headers or auth values.

## Where things live

- `config.py` -- the *only* place environment variables are read. Every
  other module receives a `Config` object or plain values, never `os.environ`
  directly.
- `constants.py` -- every non-secret, fixed implementation detail: API
  base URL/paths, rate-limit/timeout/retry tuning, env var names, config
  defaults, and formatter labels/messages. No module should have a literal
  URL, magic number, or display string inline -- add it here and import it.
  This file is for code constants only, not user configuration -- it never
  holds a token, workspace id, or webhook URL (those stay in env vars via
  `config.py`).
- `formatter.py` -- pure functions only (no network, no filesystem, no
  wall-clock reads). Takes raw entries + a project lookup + a timezone in,
  returns a Markdown string out. This is what makes it trivially testable
  with fixture data -- keep it that way.
- `toggl_client.py` / `slack_client.py` -- the only modules allowed to make
  HTTP calls.
- `main.py` -- the only orchestration layer; wires config -> fetch -> format
  -> post and owns the process exit code.
- Tests mock **all** HTTP calls (`responses` library or `unittest.mock`).
  No test should ever hit a real API.

## Explicitly out of scope (do not build)

- No MCP server.
- No Slack slash command or interactive component.
- No database or persistent storage -- this stays stateless, fetch-format-post
  per run. Don't add caching layers or a "last run" state file.
- No Cloudflare Worker.
- No YAML/JSON config file -- environment variables are the only
  configuration mechanism.

## Format stability

The Markdown table columns (`Date | Project | Tags | Description | Duration
(h:mm)`), the row sort order (date then project), the 2-decimal hour/
percentage rounding, and the summary section order (Total hours -> Hours
per project -> Hours per tag -> Hours per day) are all deliberately fixed
so a downstream reader (e.g. Claude reading the Slack channel) can compare
week-over-week output without format drift. Don't change these without a
good reason, and if you do, note it clearly since it breaks that
comparability.

Changed 2026-07: added the Tags column and per-project/per-tag percentage
+ average-hours/day figures (average is total hours for that bucket divided
by `DIGEST_PERIOD_DAYS`); dropped the "N timer(s) currently running" notice
entirely -- running entries are now silently excluded, since the digest
only reports completed time. An entry with multiple tags contributes its
full duration to each tag, so per-tag hours/percentages need not sum to
the total.
