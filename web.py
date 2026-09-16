#!/usr/bin/env python3
"""
image-to-prompt web app — Upload an image and get a generation prompt.
"""

import base64
import json
import mimetypes
import os
import time
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

from flask import Flask, Response, request, jsonify, send_from_directory, stream_with_context
from google import genai
from google.genai import types
from google.genai.errors import APIError

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

MODEL = "gemini-3.8-flash"  # free tier

# Transient server-side faults worth retrying. 504 is deliberately absent: the
# SDK reports our own client-side deadline as a 504, so retrying one just runs
# the same too-slow call again and burns the whole budget three times over.
RETRY_STATUSES = (500, 502, 503)
MAX_ATTEMPTS = 3

# 429 is deliberately NOT retried. On the free tier it means the quota window is
# exhausted, and hammering it with more requests only digs the hole deeper.
RATE_LIMIT_STATUS = 429

BUSY_MESSAGE = "Gemini 3.8 Flash is busy right now. Please try again in a moment."
RATE_LIMIT_MESSAGE = (
    "Free-tier rate limit reached for Gemini 3.8 Flash. "
    "Wait a minute before trying again."
)

MAX_PROMPT_CHARS = 4000

# The SDK retries 503s internally with its own backoff. Left on, every retry
# would stall for tens of seconds before we ever get to try again ourselves,
# so turn it off and let the loop below do the work.
HTTP_OPTIONS = types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=1))

# Hard ceiling on the whole request. Because we stream, the browser starts
# receiving text within a few seconds and this only bounds a genuine stall.
TOTAL_BUDGET_SECONDS = 90

# Never start a call that has less time left than a generation plausibly needs;
# a 3-second attempt is guaranteed to fail and just delays the error.
MIN_CALL_SECONDS = 15


def _quota_violation(e: APIError) -> dict:
    """Pull the QuotaFailure violation out of a 429, if the API sent one."""
    error = (e.details or {}).get("error", {}) if isinstance(e.details, dict) else {}
    for detail in error.get("details", []):
        if detail.get("@type", "").endswith("QuotaFailure"):
            violations = detail.get("violations") or [{}]
            return violations[0]
    return {}


def _rate_limit_message(e: APIError) -> str:
    """Say which quota ran out, because the fix differs by quota.

    Google attaches a short retryDelay (tens of seconds) even when the *daily*
    allowance is gone, so telling the user to "wait a minute" off the back of a
    daily 429 sends them back to an error that will not clear until midnight.
    """
    violation = _quota_violation(e)
    quota_id = violation.get("quotaId", "")
    limit = violation.get("quotaValue")

    if "PerDay" in quota_id:
        allowance = f" ({limit} requests/day)" if limit else ""
        return (
            f"Daily free-tier quota for {MODEL} is used up{allowance}. "
            "It resets at midnight Pacific time."
        )
    if "PerMinute" in quota_id:
        allowance = f" ({limit} requests/minute)" if limit else ""
        return (
            f"Per-minute free-tier quota for {MODEL} is used up{allowance}. "
            "Wait about a minute and try again."
        )
    return RATE_LIMIT_MESSAGE


def _log_timing(image_bytes_len: int, first_token_s: float, total_s: float, chars: int) -> None:
    """Record where a generation spent its time, so slowness is diagnosable."""
    print(
        f"[image-to-prompt] {image_bytes_len // 1024} KB image -> {chars} chars in "
        f"{total_s:.1f}s (first token {first_token_s:.1f}s, "
        f"decode {total_s - first_token_s:.1f}s)",
        flush=True,
    )


def _stream_once(client: "genai.Client", b64: str, mime_type: str, timeout_s: float):
    return client.models.generate_content_stream(
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
        config=types.GenerateContentConfig(
            # High resolution gives the model far more image tokens, which is what
            # makes subject count, pose, and fine clothing detail come out right.
            media_resolution=types.MediaResolution.MEDIA_RESOLUTION_HIGH,
            # Enough reasoning to count subjects and read poses carefully, without
            # the latency of the default "high" level.
            thinking_config=types.ThinkingConfig(thinking_level="low"),
            # Per-call deadline derived from whatever is left of the overall
            # budget, so the total can never overrun what the browser waits for.
            http_options=types.HttpOptions(timeout=int(timeout_s * 1000)),
        ),
    )


def generate_prompt_stream(image_bytes: bytes, mime_type: str):
    """Yield the prompt as Gemini produces it, as {"delta": ...} messages.

    Gemini sometimes drops a stream part-way through under load. When that
    happens the partial text is unusable, so we emit {"reset": True} and start
    over — the client throws away what it has and re-renders from scratch.
    """
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"], http_options=HTTP_OPTIONS)
    b64 = base64.standard_b64encode(image_bytes).decode()
    last = None
    deadline = time.monotonic() + TOTAL_BUDGET_SECONDS
    emitted = False  # the client is holding text from an abandoned attempt

    for attempt in range(MAX_ATTEMPTS):
        remaining = deadline - time.monotonic()
        if remaining < MIN_CALL_SECONDS:
            break

        sent = 0
        started = time.monotonic()
        try:
            for chunk in _stream_once(client, b64, mime_type, remaining):
                text = chunk.text
                if not text:
                    continue
                if sent == 0:
                    # Time to first token is prefill (image tokens + thinking);
                    # the rest is decode. Knowing which dominates is the only
                    # way to tune latency without guessing.
                    first_token_s = time.monotonic() - started
                if sent + len(text) > MAX_PROMPT_CHARS:
                    text = text[: MAX_PROMPT_CHARS - sent]
                if sent == 0 and emitted:
                    # First piece of a fresh attempt: discard the dead one.
                    yield {"reset": True}
                sent += len(text)
                emitted = True
                yield {"delta": text}
                if sent >= MAX_PROMPT_CHARS:
                    _log_timing(len(image_bytes), first_token_s, time.monotonic() - started, sent)
                    return
            if sent:
                _log_timing(len(image_bytes), first_token_s, time.monotonic() - started, sent)
                return
            # A stream that closed without producing text is as good as a fault.
            print(f"[image-to-prompt] {MODEL} returned an empty stream", flush=True)
        except APIError as e:
            if e.code == RATE_LIMIT_STATUS:
                print(f"[image-to-prompt] rate limited: {e}", flush=True)
                raise RuntimeError(_rate_limit_message(e)) from e
            if e.code not in RETRY_STATUSES:
                raise
            last = e
            where = f"after {sent} chars" if sent else "before any output"
            print(f"[image-to-prompt] {MODEL} dropped {where} ({e.code}): {e}", flush=True)

        # Back off 1s then 2s — but never past the overall budget.
        delay = 2 ** attempt
        if attempt == MAX_ATTEMPTS - 1 or time.monotonic() + delay + MIN_CALL_SECONDS > deadline:
            break
        time.sleep(delay)

    raise RuntimeError(BUSY_MESSAGE) from last


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

    def lines():
        """Newline-delimited JSON: {"delta": ...} pieces, then {"done": true}.

        A {"reset": true} line means a retry started and everything sent so far
        should be discarded.

        The status line is always 200 because the first byte leaves before we
        know whether the generation will finish, so failures are reported as a
        {"error": ...} line instead of an HTTP code.
        """
        try:
            for message in generate_prompt_stream(image_bytes, mime):
                yield json.dumps(message) + "\n"
            yield json.dumps({"done": True}) + "\n"
        except RuntimeError as e:
            # Our own "busy" / "rate limited" message — safe to show as-is.
            yield json.dumps({"error": str(e)}) + "\n"
        except APIError as e:
            print(f"[image-to-prompt] API error {e.code}: {e}", flush=True)
            yield json.dumps({"error": f"Gemini returned an error ({e.code}). Please try again."}) + "\n"
        except Exception as e:
            print(f"[image-to-prompt] unexpected: {type(e).__name__}: {e}", flush=True)
            yield json.dumps({"error": "Something went wrong generating the prompt."}) + "\n"

    return Response(
        stream_with_context(lines()),
        mimetype="application/x-ndjson",
        headers={
            # nginx buffers proxied responses by default, which would hold the
            # whole stream back and defeat the point of streaming at all.
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache",
        },
    )


if __name__ == "__main__":
    print("""
╔══════════════════════════════════════╗
║        IMAGE  →  PROMPT              ║
║         Web Application              ║
╚══════════════════════════════════════╝

Claude Code: Opus 5
Provider: Google Gemini API
Model:    gemini-3.8-flash (free tier)

Open http://localhost:5000 in your browser
""")
    app.run(debug=False, threaded=True, port=5000)
