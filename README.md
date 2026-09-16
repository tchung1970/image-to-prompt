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

**Timeouts** — three layers, so a request can never hang indefinitely:

| Layer | Limit | Purpose |
|---|---|---|
| Per API call | 20s | Ceiling on one request; a normal response takes well under 10s |
| Whole request | 45s | Checked before each retry; stops rather than starting another |
| Browser (`xhr.timeout`) | 60s | Backstop past the server budget, so the server's own message wins |

The google-genai SDK's internal retries are **disabled** (`HttpRetryOptions(attempts=1)`).
Left on, the SDK retries 503s with its own backoff, and each attempt stalls for tens of
seconds before the app regains control — which made requests hang for minutes.

**Error handling:**

- `429` (rate limit) — **not retried**. On the free tier this means the quota window is
  exhausted, and retrying only consumes more of it. Fails immediately with a message
  saying so.
- `500` / `502` / `503` / `504` — retried up to 4 times with 1s/2s/4s backoff, within the
  45s budget. `504` is usually the app's own per-call timeout surfacing as an API error.
- Anything else — raised immediately; a malformed image fails the same way on every retry.

Raw SDK errors are never shown in the UI. They are logged server-side
(`journalctl -u image-to-prompt`) and the browser gets a clean message.

## Requirements

- Python 3.10+
- `GEMINI_API_KEY` — can be placed in a local `.env` file
- `google-genai` and `flask` Python packages

## Supported Image Formats

`.jpg` `.jpeg` `.png` `.gif` `.webp` — max 10 MB per image

## Features

- Drag-and-drop or click-to-upload image input with client-side file type validation
- Live image preview with clear/regenerate controls
- One-click copy of generated prompt
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

Response: { "prompt": "..." }
Error:    { "error": "..." }
```

Error status codes: `400` bad upload, `413` too large, `502` Gemini error,
`503` rate limited or busy, `500` unexpected.

## Deployment

The live site runs on `ai.tchung.org` with the following setup:

**App directory:** `/var/www/html/image-to-prompt/`

**Systemd service** (`/etc/systemd/system/image-to-prompt.service`):
- Runs `web.py` directly with Python on port 5000
- Auto-restarts on failure (3s delay)

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
