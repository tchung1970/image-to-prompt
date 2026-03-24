# Image to Prompt

Analyze images and generate detailed AI image-generation prompts using vision models. Available as both a **CLI tool** and a **web application**.

## Overview

Given an image, the tool produces a single flowing paragraph prompt capturing subject, clothing, setting, lighting, camera/composition, style, and mood — ready to paste into Stable Diffusion, Midjourney, FLUX, etc.

## Requirements

- Python 3.10+
- API key for at least one provider:
  - **Google Gemini** (default) — set `GEMINI_API_KEY`
  - **Anthropic Claude** — set `ANTHROPIC_API_KEY`
- Keys can be placed in `~/.env` (or a local `.env` for the web app)

### Python Dependencies

| Package | Used by |
|---------|---------|
| `google-genai` | CLI (Gemini provider), Web app |
| `anthropic` | CLI (Anthropic provider) |
| `flask` | Web app only |

## Supported Image Formats

`.jpg` `.jpeg` `.png` `.gif` `.webp`

## CLI — `image-to-prompt.py`

### Usage

```bash
# Interactive mode (default provider: Gemini)
./image-to-prompt.py

# Single image
./image-to-prompt.py photo.jpg

# Entire directory (recursive)
./image-to-prompt.py ./photos/

# Use Claude instead of Gemini
./image-to-prompt.py photo.jpg --provider anthropic

# Override model
./image-to-prompt.py photo.jpg --model gemini-2.0-flash

# Save output to file
./image-to-prompt.py ./photos/ -o prompts.txt
```

### Arguments

| Argument | Description |
|----------|-------------|
| `target` | Image file, directory, or glob pattern. Omit for interactive mode. |
| `--provider`, `-p` | `gemini` (default) or `anthropic` |
| `--model` | Override the provider's default model |
| `--output`, `-o` | Write results to a file |

### Interactive Mode

When run without arguments, the tool enters an interactive loop with tab-completion for file paths. Type `q`, `quit`, or `exit` to stop.

### Default Models

| Provider | Model |
|----------|-------|
| Gemini | `gemini-2.5-flash` |

## Web App — `web.py`

A Flask-based web interface using the Gemini API.

**Live:** https://ai.tchung.org/image-to-prompt/

### Running Locally

```bash
python web.py
# Opens at http://localhost:5000
```

### Features

- Drag-and-drop or click-to-upload image input
- Live image preview with clear/regenerate controls
- One-click copy of generated prompt
- Responsive two-column layout (Catppuccin Mocha theme)
- Error handling with user-friendly messages

### API Endpoint

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
code/
├── image-to-prompt.py   # CLI tool (multi-provider)
├── web.py               # Flask web app (Gemini only)
├── index.html           # Web frontend (SPA)
└── README.md
```
