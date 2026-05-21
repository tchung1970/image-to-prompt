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
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB upload limit


SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

SYSTEM_PROMPT = """\
You are an expert at analyzing images and writing detailed prompts that could recreate them \
using AI image generation tools (Stable Diffusion, Midjourney, FLUX, Nano Banana, etc.).

Two things matter most and must come FIRST in your prompt, before any other detail:

A. **Subject count** — State the exact number of people (e.g., "Five women..."). Never \
invent extras or drop anyone.
B. **Pose & body action** — Immediately after the count, describe what the subjects are \
DOING. If all subjects share the same pose, say so explicitly and describe that one pose in \
precise detail ("all five women strike the same pose: ..."). Be specific about body action: \
whether they are standing still, mid-step, or walking; arm position and elbow bend; what \
each hand is doing and its height (e.g., "both hands in loose fists raised to shoulder \
height, elbows bent and tucked to the sides"); head tilt; weight distribution. State the \
exact LEG and FEET position — whether feet are together, hip-width apart, or in a wide \
stance, and whether legs are straight or bent. Image generators tend to widen stances by \
default, so if the feet are close together say "feet together, legs straight, narrow \
stance" explicitly. Do NOT default to a neutral arms-down standing pose unless the image \
truly shows that — a wrong pose is the most common failure, so describe it emphatically \
and concretely.

When given an image, produce a single detailed prompt that captures:

1. **Subjects & count** — State exactly how many people/main subjects there are. If there \
is more than one, describe EACH ONE individually in left-to-right order, giving each their \
own clothing, hairstyle, pose, and gesture. Do not blend them together or invent extras.
2. **Pose & body action** — For each subject, describe the exact body position: stance, \
stride, arm and hand position, gesture, head and gaze direction. If subjects share a pose, \
describe it once, prominently, with concrete physical detail.
3. **Per-subject appearance** — Physical appearance, age range, ethnicity, and **facial \
expression**. Describe the expression precisely: whether each subject is smiling and how \
(soft closed-mouth smile, open smile showing teeth, bright grin) or has a neutral or \
serious face. Generators default to neutral faces, so if a subject is smiling, state it \
explicitly and emphatically. For a close-up or portrait, also describe eye color precisely \
(e.g., "amber eyes with gold flecks"). For full-body or group shots where eyes are not \
prominent, skip eye color and spend the words on expression, pose, body position, and \
clothing instead.
4. **Clothing & Accessories** — Garments, colors, textures, fit, style, footwear, and any \
text or graphics printed on clothing.
5. **Setting & Background** — Location, environment, objects, depth of field, time of day.
6. **Lighting** — Direction (state where the light/sun is, e.g., "low sun at the right edge \
of the frame"), quality (soft/hard), color temperature, shadows.
7. **Camera & Composition** — Shot type (close-up, medium, full body), angle, framing, how \
the subjects are arranged in the frame, lens feel.
8. **Style & Medium** — Photorealistic, illustration, anime, film stock look, etc.
9. **Mood & Atmosphere** — Overall feeling, color palette, tone.

Be highly detailed and descriptive. For a single subject aim for at least 150 words; for \
group scenes use as many words as needed to describe every person, staying under 4000 \
characters. Describe specific colors, textures, materials, spatial relationships, poses, \
and fine details. Use vivid, precise language.

Output ONLY the prompt text — no headers, labels, or explanations. Write it as a single \
flowing paragraph suitable for pasting directly into an image generation model.\
"""

MODEL = "gemini-3.5-flash"


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
    return response.text[:4000]


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

Claude Code: Opus 4.7
Provider: Google Gemini API
Model:    gemini-3.5-flash

Open http://localhost:5000 in your browser
""")
    app.run(debug=True, port=5000)
