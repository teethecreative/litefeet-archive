"""Branded, text-only PNG previews for social crawlers (no fabricated portraits)."""
from functools import lru_cache
from io import BytesIO

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
        # PIL's bundled font is a deployment-safe fallback.
        return ImageFont.load_default(size=size)


@lru_cache(maxsize=2)
def render_social_card(kind):
    """Return a 1200 x 630 Open Graph PNG with consistent Vault branding."""
    if kind == "write-ins":
        lines = ("DANCER'S CHOICE", "WRITE-IN CATEGORIES")
        kicker = "2026 AWARDS"
        subtitle = "Help shape the 2026 award categories."
    elif kind == "vault":
        lines = ("PRESERVING", "LITEFEET CULTURE")
        kicker = "THE LITEFEET VAULT"
        subtitle = "Explore the people, stories and history of LiteFeet."
    else:
        raise ValueError("Unknown public social card")

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

    draw.text((446, 100), kicker, font=_font(20, True), fill=BLUE)
    y = 172
    for line in lines:
        size = 57 if len(line) < 17 else 45
        draw.text((442, y), line, font=_font(size, True), fill=NAVY)
        y += 76
    draw.rectangle((445, y + 22, 1080, y + 27), fill=GOLD)
    draw.text((446, y + 66), subtitle, font=_font(23), fill="#263c57")

    buffer = BytesIO()
    im.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
