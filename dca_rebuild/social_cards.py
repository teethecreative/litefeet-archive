"""Branded, page-specific 1200x630 social preview PNGs; no synthetic portraits."""
from functools import lru_cache
from io import BytesIO
import re
from PIL import Image, ImageDraw, ImageFont

NAVY = "#071d3b"
BLUE = "#143f80"
GOLD = "#d9ac47"
PAPER = "#f6f5f1"
WHITE = "#ffffff"

def _font(size, bold=False):
    family = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    try:
        return ImageFont.truetype(family, size)
    except OSError:
        return ImageFont.load_default(size=size)

def _wrap(draw, text, font, max_width, max_lines):
    """Bound text to the card; never let archive titles spill off the image."""
    words = re.sub(r"\s+", " ", text or "").strip().split()
    lines, current = [], ""
    for word in words:
        candidate = (current + " " + word).strip()
        if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
            if len(lines) >= max_lines:
                break
    if current and len(lines) < max_lines:
        lines.append(current)
    if len(lines) == max_lines and " ".join(lines) != " ".join(words):
        last = lines[-1]
        while last and draw.textbbox((0, 0), last + "…", font=font)[2] > max_width:
            last = last[:-1]
        lines[-1] = last.rstrip() + "…"
    return lines

@lru_cache(maxsize=128)
def render_social_card(kind, title, description):
    if kind not in ("vault", "write-ins", "page"):
        raise ValueError("Unknown preview category")
    im = Image.new("RGB", (1200, 630), PAPER)
    draw = ImageDraw.Draw(im)
    draw.rectangle((0, 0, 386, 630), fill=NAVY)
    draw.rectangle((385, 0, 394, 630), fill=GOLD)
    draw.rectangle((52, 72, 335, 77), fill=GOLD)
    draw.text((52, 110), "THE", font=_font(43, True), fill=WHITE)
    draw.text((52, 170), "LITEFEET", font=_font(42, True), fill=WHITE)
    draw.text((52, 232), "VAULT", font=_font(68, True), fill=GOLD)
    draw.line((52, 442, 335, 442), fill="#8396b1", width=2)
    draw.text((52, 466), "CULTURE. HISTORY.", font=_font(20, True), fill=WHITE)
    draw.text((52, 502), "COMMUNITY.", font=_font(20, True), fill=WHITE)
    draw.text((52, 575), "THELITEFEETVAULT.COM", font=_font(14), fill="#c9d4e2")

    title = (title or "The LiteFeet Vault").replace(" | The LiteFeet Vault Archive", "")
    title = title.replace(" | The LiteFeet Vault", "").strip()
    heading = ("WRITE-IN CATEGORIES" if kind == "write-ins" else
               "PRESERVING LITEFEET CULTURE" if kind == "vault" else title)
    kicker = ("DANCER'S CHOICE / 2026" if kind == "write-ins" else
              "THE LITEFEET VAULT" if kind == "vault" else
              "EXPLORE THE LITEFEET VAULT")
    draw.text((446, 98), kicker, font=_font(20, True), fill=BLUE)
    size = 56 if len(heading) < 30 else 46 if len(heading) < 55 else 38
    heading_font = _font(size, True)
    heading_lines = _wrap(draw, heading, heading_font, 689, 4)
    y = 167
    for line in heading_lines:
        draw.text((442, y), line, font=heading_font, fill=NAVY)
        y += size + 16
    rule_y = max(390, min(y + 12, 440))
    draw.rectangle((445, rule_y, 1080, rule_y + 5), fill=GOLD)
    subtitle_font = _font(22)
    for index, line in enumerate(_wrap(draw, description, subtitle_font, 680, 3)):
        draw.text((446, rule_y + 35 + index * 32), line, font=subtitle_font, fill="#263c57")
    buffer = BytesIO()
    im.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
