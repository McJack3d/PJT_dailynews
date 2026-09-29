"""A newspaper-style front cover (grayscale JPEG) so the issue looks like one in the Kindle
library: masthead, dateline, and the top headline of each section."""

from __future__ import annotations

import io
import logging
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

log = logging.getLogger(__name__)

WIDTH, HEIGHT = 1200, 1920  # the 1:1.6 ratio Amazon recommends
MARGIN = 90
INK, GREY, PAPER = 0, 85, 255

# Times-like faces first (Liberation Serif ships on GitHub's Ubuntu runners, Times New Roman
# on macOS), so local previews match what the workflow sends. fc-match is the last resort.
_FONTS = {
    "bold": (
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    ),
    "regular": (
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
        "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    ),
    "italic": (
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf",
        "/System/Library/Fonts/Supplemental/Times New Roman Italic.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf",
    ),
}
_FC_PATTERN = {"bold": "serif:bold", "regular": "serif", "italic": "serif:italic"}


@lru_cache
def _font_path(style: str) -> str | None:
    for path in _FONTS[style]:
        if Path(path).exists():
            return path
    if shutil.which("fc-match"):
        try:
            cmd = ["fc-match", "-f", "%{file}", _FC_PATTERN[style]]
            found = subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout
        except (OSError, subprocess.SubprocessError):
            found = ""
        if found.strip().endswith((".ttf", ".otf")):
            return found.strip()
    log.warning("No serif %s font found; the cover uses Pillow's default font", style)
    return None


def _font(style: str, size: int) -> ImageFont.FreeTypeFont:
    path = _font_path(style)
    return ImageFont.truetype(path, size) if path else ImageFont.load_default(size)


def _width(draw: ImageDraw.ImageDraw, text: str, font, tracking: int = 0) -> float:
    return draw.textlength(text, font=font) + tracking * max(0, len(text) - 1)


def _tracked(draw, x: float, y: float, text: str, font, tracking: int, fill: int) -> None:
    """Draw letter-spaced text (Pillow has no tracking option)."""
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        x += draw.textlength(ch, font=font) + tracking


def _centered(draw, y: float, text: str, font, tracking: int = 0, fill: int = INK) -> None:
    _tracked(draw, (WIDTH - _width(draw, text, font, tracking)) / 2, y, text, font, tracking, fill)


def _wrap(draw, text: str, font, width: float, max_lines: int) -> list[str]:
    lines: list[str] = []
    for word in text.split():
        if lines and _width(draw, f"{lines[-1]} {word}", font) <= width:
            lines[-1] = f"{lines[-1]} {word}"
        else:
            lines.append(word)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        while lines[-1] and _width(draw, lines[-1] + " …", font) > width:
            lines[-1] = lines[-1].rsplit(" ", 1)[0] if " " in lines[-1] else lines[-1][:-1]
        lines[-1] += " …"
    return lines


def _rule(draw, y: float, thickness: int, fill: int = INK, x0: int = MARGIN, x1: int = 0) -> None:
    draw.rectangle((x0, y, x1 or WIDTH - MARGIN, y + thickness - 1), fill=fill)


def render_cover(
    title: str, dateline: str, headlines: list[tuple[str, str, str]], footer: str
) -> bytes:
    """headlines: (section, headline, source) for each section, lead story first."""
    img = Image.new("L", (WIDTH, HEIGHT), PAPER)
    draw = ImageDraw.Draw(img)
    text_width = WIDTH - 2 * MARGIN

    # Masthead between a heavy double rule and a thin one.
    y = 100
    _rule(draw, y, 12)
    _rule(draw, y + 20, 3)
    y += 23 + 40
    size = 200
    while size > 80 and _width(draw, title, _font("bold", size)) > text_width:
        size -= 6
    mast = _font("bold", size)
    box = draw.textbbox((WIDTH / 2, y), title, font=mast, anchor="mt")
    draw.text((WIDTH / 2, y), title, font=mast, fill=INK, anchor="mt")
    y = box[3] + 44
    _rule(draw, y, 3)
    y += 3 + 24
    _centered(draw, y, dateline.upper(), _font("regular", 34), tracking=5)
    y += 34 + 26
    _rule(draw, y, 3)
    y += 3 + 70

    footer_top = HEIGHT - 170
    label_font, source_font = _font("bold", 30), _font("italic", 34)
    for n, (section, headline, source) in enumerate(headlines):
        lead = n == 0
        head_font = _font("bold", 64 if lead else 48)
        line_h = int(head_font.size * 1.16)
        lines = _wrap(draw, headline, head_font, text_width, 3)
        block = 5 + 18 + 42 + line_h * len(lines) + 12 + 44
        if y + block > footer_top - 20:
            break
        if not lead:
            _rule(draw, y - 40, 1, fill=GREY)
        _rule(draw, y, 5, x1=MARGIN + 70)
        y += 5 + 18
        _tracked(draw, MARGIN, y, section.upper(), label_font, 5, INK)
        y += 42
        for line in lines:
            draw.text((MARGIN, y), line, font=head_font, fill=INK)
            y += line_h
        y += 12
        draw.text((MARGIN, y), source, font=source_font, fill=GREY)
        y += 44 + 72

    _rule(draw, footer_top, 3)
    _centered(draw, footer_top + 34, footer.upper(), _font("regular", 30), tracking=5, fill=GREY)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88, optimize=True)
    return buf.getvalue()
