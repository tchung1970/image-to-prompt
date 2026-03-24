#!/usr/bin/env python3
"""
image-to-prompt — Analyze images and generate detailed prompts for recreating them.

Usage:
    ./image-to-prompt.py                           # interactive mode (default: gemini)
    ./image-to-prompt.py photo.jpg                 # single image
    ./image-to-prompt.py ./000/                    # entire directory
    ./image-to-prompt.py --provider anthropic       # use Claude instead
"""

import argparse
import base64
import glob
import mimetypes
import os
import sys
from pathlib import Path

# Load environment variables from ~/.env
env_file = Path.home() / ".env"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())

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

PROVIDERS = {
    "gemini": {
        "name": "Google Gemini API",
        "model": "gemini-2.5-flash",
        "env_key": "GEMINI_API_KEY",
    },
    "anthropic": {
        "name": "Claude Haiku 4.5",
        "model": "claude-haiku-4-5-20251001",
        "env_key": "ANTHROPIC_API_KEY",
    },
}

DEFAULT_PROVIDER = "gemini"

BANNER = """
╔══════════════════════════════════════╗
║        IMAGE  →  PROMPT              ║
║   Generate prompts from images       ║
╚══════════════════════════════════════╝"""


def encode_image(path: Path) -> tuple[str, str]:
    """Read and base64-encode an image, returning (base64_data, media_type)."""
    mime, _ = mimetypes.guess_type(str(path))
    if mime is None:
        mime = "image/jpeg"
    with open(path, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode("utf-8")
    return data, mime


def generate_prompt_anthropic(image_path: Path, model: str) -> str:
    """Use Claude to analyze image."""
    import anthropic
    client = anthropic.Anthropic()
    b64_data, media_type = encode_image(image_path)

    message = client.messages.create(
        model=model,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": b64_data,
                        },
                    },
                    {
                        "type": "text",
                        "text": "Analyze this image and write a detailed prompt to recreate it.",
                    },
                ],
            }
        ],
    )
    return message.content[0].text


def generate_prompt_gemini(image_path: Path, model: str) -> str:
    """Use Gemini to analyze image."""
    from google import genai
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    with open(image_path, "rb") as f:
        image_bytes = f.read()

    mime, _ = mimetypes.guess_type(str(image_path))
    if mime is None:
        mime = "image/jpeg"

    response = client.models.generate_content(
        model=model,
        contents=[
            {
                "role": "user",
                "parts": [
                    {"inline_data": {"mime_type": mime, "data": base64.standard_b64encode(image_bytes).decode()}},
                    {"text": SYSTEM_PROMPT + "\n\nAnalyze this image and write a detailed prompt to recreate it."},
                ],
            }
        ],
    )
    return response.text


def generate_prompt(image_path: Path, provider: str, model: str) -> str:
    """Route to the correct provider."""
    if provider == "anthropic":
        return generate_prompt_anthropic(image_path, model)
    elif provider == "gemini":
        return generate_prompt_gemini(image_path, model)
    else:
        raise ValueError(f"Unknown provider: {provider}")


def collect_images(target: Path) -> list[Path]:
    """Return a sorted list of supported image files from a path or directory."""
    if target.is_file():
        if target.suffix.lower() in SUPPORTED_EXTENSIONS:
            return [target]
        return []

    if target.is_dir():
        return sorted(
            p for p in target.rglob("*") if p.suffix.lower() in SUPPORTED_EXTENSIONS
        )

    # Try glob expansion (e.g., *.jpg)
    expanded = sorted(Path(p) for p in glob.glob(str(target)))
    return [p for p in expanded if p.suffix.lower() in SUPPORTED_EXTENSIONS]


def prompt_for_path() -> str:
    """Ask the user for an image path with tab-completion support."""
    try:
        import readline
        readline.set_completer_delims(" \t\n")
        readline.parse_and_bind("tab: complete")

        def path_completer(text, state):
            line = text
            if not line:
                line = "./"
            p = Path(line)
            if line.endswith("/") or p.is_dir():
                parent = p
                prefix = ""
            else:
                parent = p.parent
                prefix = p.name
            try:
                matches = []
                for item in sorted(parent.iterdir()):
                    name = item.name
                    if prefix and not name.lower().startswith(prefix.lower()):
                        continue
                    full = str(parent / name)
                    if item.is_dir():
                        full += "/"
                    matches.append(full)
                if state < len(matches):
                    return matches[state]
            except (OSError, PermissionError):
                pass
            return None

        readline.set_completer(path_completer)
    except ImportError:
        pass

    default = "image.jpg"
    user_input = input(f"\nEnter image name or press enter to accept default or 'q' to quit: ").strip()
    return user_input if user_input else default


def process_images(images: list[Path], provider: str, model: str, output: Path | None = None):
    """Process a list of images and print/save results."""
    output_lines = []

    for i, img_path in enumerate(images):
        if len(images) > 1:
            header = f"--- {img_path.name} ---"
            print(f"\n[{i+1}/{len(images)}] Processing {img_path.name}...")
        else:
            header = None
            print(f"\nProcessing {img_path.name}...")

        try:
            prompt_text = generate_prompt(img_path, provider, model)
        except Exception as e:
            print(f"  Error: {e}")
            continue

        if header:
            output_lines.append(header)
        output_lines.append(prompt_text)
        output_lines.append("")

        # Print result immediately
        print(f"\n{prompt_text}\n")

    if output and output_lines:
        result = "\n".join(output_lines).strip() + "\n"
        output.write_text(result)
        print(f"Saved to {output}")


def interactive_mode(provider: str, model: str):
    """Run in interactive loop — keep asking for images until user quits."""
    info = PROVIDERS[provider]
    print(BANNER)
    print()
    print("Claude Code: Opus 4.6")
    print(f"Provider: Google Gemini API")
    print(f"Model:    {model}")
    print("Default:  image.jpg")
    print("Supports: .jpg .jpeg .png .gif .webp")

    while True:
        try:
            user_input = prompt_for_path()
        except (KeyboardInterrupt, EOFError):
            print("\nBye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("q", "quit", "exit"):
            print("Bye!")
            break

        target = Path(user_input).expanduser()
        images = collect_images(target)

        if not images:
            print(f"  No supported images found at: {user_input}")
            print(f"  Supported formats: {', '.join(sorted(SUPPORTED_EXTENSIONS))}")
            continue

        print(f"  Found {len(images)} image(s)")
        process_images(images, provider, model)


def main():
    parser = argparse.ArgumentParser(
        description="Generate image-recreation prompts from images using AI vision."
    )
    parser.add_argument(
        "target",
        nargs="?",
        type=Path,
        default=None,
        help="Image file or directory (omit for interactive mode)",
    )
    parser.add_argument(
        "--provider", "-p",
        choices=list(PROVIDERS.keys()),
        default=DEFAULT_PROVIDER,
        help=f"AI provider (default: {DEFAULT_PROVIDER})",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Override model name (default: provider's default)",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="Write output to file",
    )
    args = parser.parse_args()

    provider = args.provider
    model = args.model or PROVIDERS[provider]["model"]
    env_key = PROVIDERS[provider]["env_key"]

    if not os.environ.get(env_key):
        print(f"Error: {env_key} not set. Add it to ~/.env", file=sys.stderr)
        sys.exit(1)

    if args.target is None:
        interactive_mode(provider, model)
    else:
        images = collect_images(args.target)
        if not images:
            print(f"No supported images found at: {args.target}")
            sys.exit(1)
        process_images(images, provider, model, args.output)


if __name__ == "__main__":
    main()
