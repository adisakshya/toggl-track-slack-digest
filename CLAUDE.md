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
- **`/me/time_entries` caps at 1000 results per call**, with no error
  signaled when the cap is hit -- a capped response can't be trusted as
  complete. `get_time_entries` fails loudly (`TogglAPIError`) rather than
  silently posting an under-reported digest. Don't add auto-pagination
  here (it would multiply `/me/*` requests against the 30/hour budget
  above) -- point users at narrowing `DIGEST_PERIOD_DAYS` or
  `TOGGL_PROJECT_IDS` instead.
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
  wall-clock reads). Takes raw entries + a project lookup + a timezone +
  the window dates in, returns `(blocks, text)`: a Slack Block Kit block
  list plus a complete plain-text fallback mirroring the same data. This
  is what makes it trivially testable with fixture data -- keep it that
  way.
- `toggl_client.py` / `slack_client.py` -- the only modules allowed to make
  HTTP calls. `slack_client` posts the Block Kit `blocks` and the `text`
  fallback in one Incoming Webhook payload.
- `main.py` -- the only orchestration layer; wires config -> fetch -> format
  -> post and owns the process exit code.
- Tests mock **all** HTTP calls (`responses` library or `unittest.mock`).
  No test should ever hit a real API.

## Explicitly out of scope (do not build)

- No MCP server.
- No Slack slash command or interactive component. (Block Kit *layout*
  blocks -- header/section/divider/context -- are used for rendering;
  that's fine. Interactive elements -- buttons, select menus, actions --
  are not, and would need a bot token / request handling this stateless
  job doesn't have.)
- No database or persistent storage -- this stays stateless, fetch-format-post
  per run. Don't add caching layers or a "last run" state file.
- No Cloudflare Worker.
- No YAML/JSON config file -- environment variables are the only
  configuration mechanism.

## Format stability

The digest is **aggregate-only** (no per-entry rows). The section order
(header/range → anomaly flags → By Project → By Tag → By Day), the
descending-by-hours ordering within Project/Tag, the chronological By Day
order, the `Xh Ym` duration format, and the 2-decimal percentage /
avg-hours-per-day rounding are all deliberately fixed so a downstream
reader (primarily Claude reading the Slack channel for week-over-week
insights) can compare output without format drift. The `text` fallback is
the complete, markup-free mirror an LLM parses; keep it in sync with the
`blocks`. Don't change these without a good reason, and if you do, note it
clearly since it breaks comparability.

Changed 2026-07: the per-project/per-tag/per-day breakdown carries
percentage of total, average-hours/day (bucket hours ÷
`DIGEST_PERIOD_DAYS`), and an entry count. Running entries are silently
excluded (completed time only). Entries are grouped into a tag bucket by
their exact set of tags, sorted alphabetically and comma-joined (so an
entry tagged both "OLI Delivery" and "CSL Behring" rolls into one
"CSL Behring, OLI Delivery" row) -- per-tag-group hours/percentages sum to
the total, same as per-project. A day whose completed hours meet or exceed
`ANOMALY_THRESHOLD_HOURS` (default 16) gets a "forgotten running timer"
warning. Later in 2026-07 the per-entry Markdown table was dropped
entirely and output moved to Slack Block Kit (native rendering) plus the
plain-text fallback.
