#!/usr/bin/env python3
"""
image-to-prompt web app — Upload an image and get a generation prompt.
"""

import base64
import mimetypes
import os
from pathlib import Path

# Load environment variables from .env (local first, then ~/.env)
app_dir = Path(__file__).parent
env_file = app_dir / ".env" if (app_dir / ".env").exists() else Path.home() / ".env"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())

from flask import Flask, request, jsonify, send_from_directory
from google import genai

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 MB upload limit

UPLOAD_DIR = Path(__file__).parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

SYSTEM_PROMPT = """\
You are an expert at analyzing images and writing detailed prompts that could recreate them \
using AI image generation tools (Stable Diffusion, Midjourney, FLUX, etc.).

When given an image, produce a single detailed prompt that captures:

1. **Subject** — Who/what is in the image, physical appearance, attractiveness, expression, pose, age range, ethnicity
2. **Clothing & Accessories** — Garments, colors, textures, fit, style
3. **Setting & Background** — Location, environment, objects, depth of field
4. **Lighting** — Direction, quality (soft/hard), color temperature, shadows
5. **Camera & Composition** — Shot type (close-up, medium, full body), angle, framing, lens feel
6. **Style & Medium** — Photorealistic, illustration, anime, film stock look, etc.
7. **Mood & Atmosphere** — Overall feeling, color palette, tone

Output ONLY the prompt text — no headers, labels, or explanations. Write it as a single \
flowing paragraph suitable for pasting directly into an image generation model.\
"""

MODEL = "gemini-2.5-flash"


def generate_prompt(image_bytes: bytes, mime_type: str) -> str:
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    b64 = base64.standard_b64encode(image_bytes).decode()

    response = client.models.generate_content(
        model=MODEL,
        contents=[
            {
                "role": "user",
                "parts": [
                    {"inline_data": {"mime_type": mime_type, "data": b64}},
                    {"text": SYSTEM_PROMPT + "\n\nAnalyze this image and write a detailed prompt to recreate it."},
                ],
            }
        ],
    )
    return response.text


@app.route("/")
def index():
    return send_from_directory(Path(__file__).parent, "index.html")



@app.route("/generate", methods=["POST"])
def generate():
    if "image" not in request.files:
        return jsonify({"error": "No image uploaded"}), 400

    file = request.files["image"]
    if not file.filename:
        return jsonify({"error": "No file selected"}), 400

    ext = Path(file.filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        return jsonify({"error": f"Unsupported format. Use: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"}), 400

    mime = mimetypes.guess_type(file.filename)[0] or "image/jpeg"
    image_bytes = file.read()

    max_size = app.config["MAX_CONTENT_LENGTH"]
    if len(image_bytes) > max_size:
        return jsonify({"error": f"Image too large. Maximum size is {max_size // (1024 * 1024)} MB."}), 413

    try:
        prompt_text = generate_prompt(image_bytes, mime)
        return jsonify({"prompt": prompt_text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    print("""
╔══════════════════════════════════════╗
║        IMAGE  →  PROMPT              ║
║         Web Application              ║
╚══════════════════════════════════════╝

Claude Code: Opus 4.6
Provider: Google Gemini API
Model:    gemini-2.5-flash

Open http://localhost:5000 in your browser
""")
    app.run(debug=True, port=5000)
