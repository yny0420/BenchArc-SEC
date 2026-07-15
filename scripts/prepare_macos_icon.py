#!/usr/bin/env python3
"""Add the transparent macOS squircle boundary to the white icon artwork."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


APP_DIR = Path(__file__).resolve().parent.parent
SOURCE = APP_DIR / "assets" / "BenchArc_SEC_icon_white_source.png"
OUTPUT = APP_DIR / "assets" / "BenchArc_SEC_icon_white_transparent.png"
SIZE = 1024
SUPERSAMPLE = 4


def main() -> None:
    image = Image.open(SOURCE).convert("RGBA")
    image = image.resize((SIZE, SIZE), Image.Resampling.LANCZOS)

    mask = Image.new("L", (SIZE * SUPERSAMPLE, SIZE * SUPERSAMPLE), 0)
    draw = ImageDraw.Draw(mask)
    box = tuple(value * SUPERSAMPLE for value in (72, 55, 952, 963))
    draw.rounded_rectangle(box, radius=205 * SUPERSAMPLE, fill=255)
    mask = mask.resize((SIZE, SIZE), Image.Resampling.LANCZOS)
    image.putalpha(mask)
    image.save(OUTPUT)
    print(f"Built: {OUTPUT}")


if __name__ == "__main__":
    main()
