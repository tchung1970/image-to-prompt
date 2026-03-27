# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Image-to-Prompt is a Flask + vanilla JS single-page app that accepts an image upload and returns an AI-generated image-generation prompt via the Google Gemini API (`gemini-2.5-flash`). Live at https://ai.tchung.org/image-to-prompt/.

## Running Locally

```bash
python web.py          # serves on http://localhost:5000
```

Requires `GEMINI_API_KEY` in a `.env` file (checked in app directory first, then `~/.env`). Python dependencies: `flask`, `google-genai`.

## Architecture

Two-file app — no build step, no bundler, no database:

- **`web.py`** — Flask backend. Serves `index.html` at `/`, exposes `POST /generate` which reads the uploaded image, base64-encodes it, sends it to Gemini with a system prompt, and returns `{"prompt": "..."}`. Loads env vars from `.env` manually (no `python-dotenv` dependency).
- **`index.html`** — Self-contained SPA (HTML + CSS + JS in one file). Drag-and-drop/click image upload, preview, calls `/generate`, displays result with copy button. Catppuccin Mocha color scheme, Inter font, responsive two-column grid.

## Deployment

Deployed to `ai.tchung.org` via scp + systemd restart:

```bash
scp web.py index.html README.md root@ai:/var/www/html/image-to-prompt/
ssh root@ai "systemctl restart image-to-prompt"
```

Nginx reverse proxies `/image-to-prompt/` to port 5000 with 10MB body limit and 120s timeout.
