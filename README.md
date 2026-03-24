# Image to Prompt

Analyze images and generate detailed AI image-generation prompts using Google Gemini.

**Live:** https://ai.tchung.org/image-to-prompt/

## Overview

Given an image, the tool produces a single flowing paragraph prompt capturing subject, clothing, setting, lighting, camera/composition, style, and mood — ready to paste into Stable Diffusion, Midjourney, FLUX, etc.

## Requirements

- Python 3.10+
- `GEMINI_API_KEY` — can be placed in a local `.env` file
- `google-genai` and `flask` Python packages

## Supported Image Formats

`.jpg` `.jpeg` `.png` `.gif` `.webp`

## Features

- Drag-and-drop or click-to-upload image input
- Live image preview with clear/regenerate controls
- One-click copy of generated prompt
- Responsive two-column layout (Catppuccin Mocha theme)
- Error handling with user-friendly messages

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

## Deployment

The live site runs on `ai.tchung.org` with the following setup:

**App directory:** `/var/www/html/image-to-prompt/`

**Systemd service** (`/etc/systemd/system/image-to-prompt.service`):
- Runs `web.py` directly with Python on port 5000
- Auto-restarts on failure (3s delay)

**Nginx** reverse proxy:
- `/image-to-prompt/` → `http://127.0.0.1:5000/`
- 120s read/send timeout for long AI generation requests

**Environment:** Hidden `.env` file in the app directory (`chmod 600`) with `GEMINI_API_KEY`

### Deploying Updates

```bash
# Copy files to server
scp web.py index.html README.md root@ai:/var/www/html/image-to-prompt/

# Restart the service (required — Flask serves all files including README.md)
ssh root@ai "systemctl restart image-to-prompt"
```

## Project Structure

```
├── web.py        # Flask web app
├── index.html    # Web frontend (SPA)
└── README.md
```
