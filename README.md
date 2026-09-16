# Image to Prompt

Analyze images and generate detailed AI image-generation prompts using Google Gemini API (gemini-3.8-flash).

**Live:** https://ai.tchung.org/image-to-prompt/

## Overview

Given an image, the tool produces a single flowing paragraph prompt capturing subject, clothing, setting, lighting, camera/composition, style, and mood — ready to paste into Nano Banana Pro, Nano Banana 2, etc.

## AI Model

- [**Google Gemini 3.8 Flash**](https://ai.google.dev/gemini-api/docs/pricing#gemini-3.8-flash) (`gemini-3.8-flash`) — free tier

  This is the only model used. Upgraded from `gemini-3.5-flash` for more accurate image
  analysis and prompt detail.

  Request config:
  - `media_resolution=HIGH` — more image tokens, which is what makes subject count, pose,
    and fine clothing detail come out right. Costs nothing on the free tier but consumes
    token quota faster.
  - `thinking_level=low` — Gemini 3.x defaults to `high`; `low` keeps latency down without
    hurting a description task.

## Reliability

The free tier returns errors often enough that the app has to handle them explicitly.

### Streaming

The response is **streamed**, which is what keeps the app responsive. A non-streaming call
with `media_resolution=HIGH` takes ~32s, long enough that the browser gave up before the
server answered. Streaming puts the first words on screen in ~7s and the full prompt in
under 10s.

`/generate` returns newline-delimited JSON as the model produces it:

```
{"delta": "One glowing snail, positioned "}
{"delta": "in profile facing toward the right, "}
{"done": true}
```

- `{"delta": ...}` — the next piece of prompt text, appended by the client
- `{"reset": true}` — the generation was dropped mid-stream and restarted; the client
  discards what it has and re-renders from scratch
- `{"error": ...}` — generation failed. The HTTP status is always `200` because the first
  byte leaves before the outcome is known, so failures ride in the body
- `{"done": true}` — the prompt is complete. A stream that ends **without** this line is a
  truncation, and the client says so rather than presenting a fragment as finished

The response sets `X-Accel-Buffering: no`; without it nginx buffers the whole stream and
delivers it in one piece, defeating the point.

**In-flight state is visible in the UI.** While text is arriving, a caret blinks after it,
the header reads `generating...`, Copy is disabled, and the counter shows
`884 characters...` rather than `884 / 4000`. Only `{"done": true}` finalizes it. Without
this, a partial prompt is indistinguishable from a short finished one.

### Timeouts

| Layer | Limit | Purpose |
|---|---|---|
| Per API call | remaining budget | Derived from what is left of the total, so calls cannot overrun it |
| Whole request | 90s | Checked before each attempt; stops rather than starting another |
| Browser (`xhr.timeout`) | 120s | Backstop past the server budget, so the server's own message wins |
| gunicorn `--timeout` | 180s | Above all of the above, or the worker is killed mid-generation |

A call is only started with at least `MIN_CALL_SECONDS` (15s) left — a 3s attempt is
guaranteed to fail and only delays the error.

The google-genai SDK's internal retries are **disabled** (`HttpRetryOptions(attempts=1)`).
Left on, the SDK retries 503s with its own backoff, and each attempt stalls for tens of
seconds before the app regains control — which made requests hang for minutes.

### Error handling

- `429` (rate limit) — **not retried**. The message distinguishes the *daily* quota from
  the *per-minute* one by reading `quotaId` out of the `QuotaFailure` detail. This matters:
  Google attaches a short `retryDelay` (~38s) even to a daily 429, so a generic "wait a
  minute" sends the user back to an error that will not clear until midnight Pacific.
- `500` / `502` / `503` — retried up to 3 times with 1s/2s backoff, within the 90s budget.
  A drop that happens **mid-stream** also retries, emitting `{"reset": true}` first.
- `504` — **not** retried. The SDK reports the app's own client-side deadline as a 504, so
  retrying one just re-runs the same too-slow call and burns the budget three times over.
- Anything else — raised immediately; a malformed image fails the same way on every retry.

Raw SDK errors are never shown in the UI. They are logged server-side
(`journalctl -u image-to-prompt`) and the browser gets a clean message.

### Free-tier quota

`gemini-3.8-flash` allows **20 requests/day** on the free tier
(`GenerateRequestsPerDayPerProjectPerModel-FreeTier`), resetting at midnight Pacific. A
short round of testing exhausts it, so verify frontend changes against a local mock that
emits the same NDJSON rather than spending real calls.

## Requirements

- Python 3.10+
- `GEMINI_API_KEY` — can be placed in a local `.env` file
- `google-genai` and `flask` Python packages
- `gunicorn` in production (`apt install gunicorn`); `python web.py` uses Flask's built-in
  server, which is fine locally

## Supported Image Formats

`.jpg` `.jpeg` `.png` `.gif` `.webp` — max 10 MB per image

## Features

- Drag-and-drop or click-to-upload image input with client-side file type validation
- Live image preview with clear/regenerate controls
- Live streaming output: the prompt writes itself on screen as the model produces it,
  with a blinking caret and a `generating...` marker while it is still arriving
- One-click copy of generated prompt (disabled until the prompt is complete)
- Character count display (4000 character limit)
- Aspect ratio badge shown on upload: reads the image's real pixel dimensions and
  snaps to the nearest generator-supported ratio (1:1, 5:4, 4:3, 3:2, 16:9, 21:9
  and their portrait counterparts)
- Multi-subject scenes: counts people and describes each one individually
- Pose-first prompting: front-loads body action, stance, and gesture for accurate poses
- Accurate eye color detection for portraits and close-ups
- Upload progress bar
- Responsive two-column layout (Catppuccin Mocha theme)
- Error handling with dismissible messages (OK button to close)

## Running Locally

```bash
python web.py
# Opens at http://localhost:5000
```

## API Endpoint

```
POST /generate
Content-Type: multipart/form-data
Field: image (file)

Response: 200, application/x-ndjson — see "Streaming" above
```

Upload validation still fails with a plain JSON body and a real status code: `400` bad
upload, `413` too large. Once streaming begins the status is always `200` and failures
arrive as an `{"error": ...}` line, so the client checks `Content-Type` to tell the two
apart.

## Deployment

The live site runs on `ai.tchung.org` with the following setup:

**App directory:** `/var/www/html/image-to-prompt/`

**Systemd service** (`/etc/systemd/system/image-to-prompt.service`):
- Runs under **gunicorn**, not the Flask dev server:
  `gunicorn --workers 2 --threads 4 --timeout 180 --graceful-timeout 30 --bind 127.0.0.1:5000 web:app`
- `--timeout 180` must stay above the app's own `TOTAL_BUDGET_SECONDS`, or gunicorn kills
  the worker mid-generation
- Threaded workers keep one slow generation from queueing everyone else behind it
- Auto-restarts on failure (3s delay)

`debug=True` on the dev server was both single-threaded and left the Werkzeug debugger
exposed on a public host.

**Nginx** reverse proxy:
- `/image-to-prompt/` → `http://127.0.0.1:5000/`
- `client_max_body_size 10M` to allow image uploads up to 10 MB
- 120s read/send timeout for long AI generation requests

**Environment:** Hidden `.env` file in the app directory (`chmod 600`) with `GEMINI_API_KEY`

### Deploying Updates

```bash
# Copy files to server
scp web.py index.html root@ai:/var/www/html/image-to-prompt/

# scp as root leaves the files root-owned — restore ownership, then restart
ssh root@ai "cd /var/www/html/image-to-prompt \
  && chown tchung:tchung web.py index.html && chmod 644 web.py index.html \
  && systemctl restart image-to-prompt"
```

## Project Structure

```
├── web.py        # Flask web app
├── index.html    # Web frontend (SPA)
└── README.md
```
