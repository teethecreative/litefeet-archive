"""Sitewide favicon, consistent public link previews and Instagram-ready share graphics.

Does not expose private/admin pages for social sharing or modify site content.
"""
from functools import lru_cache
from html import escape, unescape
from io import BytesIO
import re

from flask import Response, abort, request, send_from_directory
from PIL import Image, ImageDraw

from dca_rebuild.seo import SITE_URL, card_key_for_path, metadata_for_path, path_for_card_key
from dca_rebuild.social_cards import _font, _wrap, render_social_card

VERSION = "20261109"
ICON_LINK = re.compile(
    r'<link\b(?=[^>]*\brel\s*=\s*(["\'])(?:icon|shortcut\s+icon|apple-touch-icon)\1)[^>]*>',
    re.I,
)
CANONICAL_LINK = re.compile(
    r'<link\b(?=[^>]*\brel\s*=\s*(["\'])canonical\1)[^>]*>', re.I,
)
SHARE_META = re.compile(
    r'<meta\b(?=[^>]*\b(?:name|property)\s*=\s*(["\'])(?:description|og:[^"\']+|twitter:[^"\']+)\1)[^>]*>',
    re.I,
)
THEME_META = re.compile(
    r'<meta\b(?=[^>]*\bname\s*=\s*(["\'])theme-color\1)[^>]*>', re.I,
)
TITLE = re.compile(r'<title\b[^>]*>.*?</title>', re.I | re.S)
DESCRIPTION = re.compile(
    r'<meta\b(?=[^>]*\bname\s*=\s*(["\'])description\1)[^>]*>', re.I,
)
CONTENT_ATTR = re.compile(r'\bcontent\s*=\s*(["\'])(.*?)\1', re.I | re.S)
PRIVATE_PREFIXES = ("/admin", "/beta", "/account", "/newsletter", "/health")
PRIVATE_PATHS = {"/submit/thank-you", "/awards/litefeet-awards/submit"}


def _public_page(path):
    return not (
        path in PRIVATE_PATHS
        or any(path == part or path.startswith(part + "/") for part in PRIVATE_PREFIXES)
        or path.endswith("/check-email")
    )


def _fallback_title(path):
    pieces = [p.replace("-", " ").replace("_", " ") for p in path.split("/") if p]
    if not pieces:
        return "The LiteFeet Vault"
    subject = pieces[-1].title()
    if subject.isdigit() and len(pieces) > 1:
        subject = pieces[-2].title() + " " + subject
    return subject + " | The LiteFeet Vault"


def _metadata(path, html=""):
    known = metadata_for_path(path, request.args.get("view") if html else None)
    if known:
        return known
    match = TITLE.search(html)
    title = unescape(re.sub(r'<[^>]+>', '', match.group(0))[0:180]).strip() if match else ""
    title = re.sub(r'\bLiteFeet Ledger\b', 'The LiteFeet Vault', title, flags=re.I)
    title = title or _fallback_title(path)
    description = ""
    found = DESCRIPTION.search(html)
    if found:
        value = CONTENT_ATTR.search(found.group(0))
        if value:
            description = unescape(value.group(2)).strip()
    description = re.sub(r'\bLiteFeet Ledger\b', 'The LiteFeet Vault', description, flags=re.I)
    description = description[:200] or (
        "Discover " + title.split(" | ")[0] + " on The LiteFeet Vault, "
        "preserving LiteFeet culture, history and community knowledge."
    )
    return {
        "title": title,
        "description": description,
        "canonical": SITE_URL + path,
        "image": SITE_URL + "/social/site/" + card_key_for_path(path) + ".png",
        "image_alt": title + " — The LiteFeet Vault",
    }


def _favicon_markup():
    root = "/static/"
    return "\n".join((
        '<link rel="icon" href="/favicon.ico?v=' + VERSION + '" sizes="any">',
        '<link rel="icon" type="image/png" sizes="32x32" href="' + root + 'favicon-32x32.png?v=' + VERSION + '">',
        '<link rel="icon" type="image/png" sizes="16x16" href="' + root + 'favicon-16x16.png?v=' + VERSION + '">',
        '<link rel="apple-touch-icon" sizes="180x180" href="' + root + 'apple-touch-icon.png?v=' + VERSION + '">',
        '<link rel="manifest" href="/site.webmanifest?v=' + VERSION + '">',
        '<meta name="theme-color" content="#071d3b">',
    ))


def _social_markup(meta):
    def tag(key, value, prop=False):
        attr = "property" if prop else "name"
        return '<meta ' + attr + '="' + key + '" content="' + escape(str(value), quote=True) + '">'
    image = meta["image"]
    entries = [
        '<link rel="canonical" href="' + escape(meta["canonical"], quote=True) + '">',
        tag("description", meta["description"]),
        tag("og:type", "website", True),
        tag("og:site_name", "The LiteFeet Vault", True),
        tag("og:locale", "en_US", True),
        tag("og:title", meta["title"], True),
        tag("og:description", meta["description"], True),
        tag("og:url", meta["canonical"], True),
        tag("og:image", image, True),
        tag("og:image:secure_url", image, True),
        tag("og:image:type", "image/png", True),
        tag("og:image:width", "1200", True),
        tag("og:image:height", "630", True),
        tag("og:image:alt", meta["image_alt"], True),
        tag("twitter:card", "summary_large_image"),
        tag("twitter:url", meta["canonical"]),
        tag("twitter:title", meta["title"]),
        tag("twitter:description", meta["description"]),
        tag("twitter:image", image),
        tag("twitter:image:alt", meta["image_alt"]),
    ]
    return "\n".join(entries)


SHARE_UI = """
<div class="lfv-share-entry"><button type="button" id="lfv-share-open" aria-haspopup="dialog">Share this page</button></div>
<dialog class="lfv-share-dialog" id="lfv-share-dialog" aria-labelledby="lfv-share-title">
  <div class="lfv-share-heading">
    <div><p class="lfv-share-eyebrow">THE LITEFEET VAULT</p><h2 id="lfv-share-title">Share this page</h2></div>
    <button class="lfv-share-close" type="button" id="lfv-share-close" aria-label="Close sharing">×</button>
  </div>
  <p class="lfv-share-copy">Create a graphic to share on Instagram, or copy the page link.</p>
  <div class="lfv-share-formats" aria-label="Instagram graphic format">
    <button type="button" data-lfv-format="story" aria-pressed="true">Story</button>
    <button type="button" data-lfv-format="post" aria-pressed="false">Post</button>
  </div>
  <img class="lfv-share-preview" id="lfv-share-preview" alt="Preview of the Instagram sharing graphic" loading="lazy">
  <div class="lfv-share-actions">
    <button type="button" id="lfv-share-image">Share image</button>
    <button type="button" id="lfv-save-image">Save image</button>
    <button type="button" id="lfv-copy-link">Copy link</button>
  </div>
  <p class="lfv-share-hint">On your phone, select Instagram from the share sheet if available. You can also save the image and upload it to Instagram.</p>
  <p class="lfv-share-status" id="lfv-share-status" role="status" aria-live="polite"></p>
</dialog>
"""


@lru_cache(maxsize=32)
def _instagram_card(format_name, title, description):
    if format_name not in ("story", "post"):
        raise ValueError("Invalid Instagram format")
    width = 1080
    height = 1920 if format_name == "story" else 1350
    image = Image.new("RGB", (width, height), "#f6f5f1")
    draw = ImageDraw.Draw(image)
    navy, blue, gold = "#071d3b", "#143f80", "#d9ac47"
    draw.rectangle((0, 0, width, 250), fill=navy)
    draw.rectangle((0, 246, width, 257), fill=gold)
    draw.text((85, 82), "THE LITEFEET", font=_font(65, True), fill="#ffffff")
    draw.text((85, 156), "VAULT", font=_font(66, True), fill=gold)
    draw.text((84, 345), "FROM THE VAULT", font=_font(31, True), fill=blue)
    clean_title = re.sub(r'\s*\|\s*The LiteFeet Vault.*$', '', title, flags=re.I)
    font_size = 78 if len(clean_title) < 35 else 66 if len(clean_title) < 60 else 56
    font = _font(font_size, True)
    cursor = 440
    max_lines = 7 if format_name == "story" else 5
    for line in _wrap(draw, clean_title, font, 910, max_lines):
        draw.text((80, cursor), line, font=font, fill=navy)
        cursor += font_size + 20
    rule_y = max(cursor + 30, 890 if format_name == "story" else 770)
    rule_y = min(rule_y, height - 350)
    draw.rectangle((85, rule_y, 995, rule_y + 7), fill=gold)
    desc_font = _font(35)
    for i, line in enumerate(_wrap(draw, description, desc_font, 905, 4 if format_name == "story" else 3)):
        draw.text((85, rule_y + 54 + i * 56), line, font=desc_font, fill="#344b62")
    draw.rectangle((0, height - 230, width, height), fill=navy)
    draw.text((85, height - 171), "EXPLORE THE CULTURE", font=_font(42, True), fill="#ffffff")
    draw.text((85, height - 105), "THELITEFEETVAULT.COM", font=_font(32), fill=gold)
    out = BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def install_sharing(app):
    """Install once, after the app's ordinary public routes are registered."""

    @app.get("/favicon.ico")
    def vault_favicon():
        return send_from_directory(app.static_folder, "favicon.ico", mimetype="image/x-icon")

    @app.get("/site.webmanifest")
    def vault_manifest():
        return send_from_directory(app.static_folder, "site.webmanifest", mimetype="application/manifest+json")

    @app.get("/social/site/<card>.png")
    def vault_fallback_social_card(card):
        path = path_for_card_key(card)
        if not path or len(card) > 210 or not _public_page(path):
            abort(404)
        meta = metadata_for_path(path)
        if not meta:
            meta = _metadata(path)
        return Response(
            render_social_card("vault" if path == "/" else "page", meta["title"], meta["description"]),
            mimetype="image/png",
            headers={"Cache-Control": "public, max-age=86400", "X-Content-Type-Options": "nosniff"},
        )

    @app.get("/social/instagram/<format_name>/<card>.png")
    def vault_instagram_card(format_name, card):
        path = path_for_card_key(card)
        if format_name not in ("story", "post") or not path or len(card) > 210 or not _public_page(path):
            abort(404)
        meta = metadata_for_path(path) or _metadata(path)
        return Response(
            _instagram_card(format_name, meta["title"], meta["description"]),
            mimetype="image/png",
            headers={"Cache-Control": "public, max-age=86400", "X-Content-Type-Options": "nosniff"},
        )

    @app.after_request
    def vault_share_branding(response):
        if request.method != "GET" or response.status_code != 200 or response.direct_passthrough:
            return response
        if "text/html" not in response.content_type.lower():
            return response
        html = response.get_data(as_text=True)
        if not re.search(r"</head\s*>", html, re.I):
            return response
        html = ICON_LINK.sub("", html)
        html = THEME_META.sub("", html)
        branding = _favicon_markup()
        if _public_page(request.path):
            meta = _metadata(request.path, html)
            html = CANONICAL_LINK.sub("", html)
            html = SHARE_META.sub("", html)
            if TITLE.search(html):
                html = TITLE.sub("<title>" + escape(meta["title"]) + "</title>", html, count=1)
            branding += "\n" + _social_markup(meta)
            branding += '\n<link rel="stylesheet" href="/static/css/vault-share.css?v=' + VERSION + '">'
            branding += '\n<script defer src="/static/js/vault-share.js?v=' + VERSION + '"></script>'
            html = re.sub(r"</body\s*>", lambda match: SHARE_UI + match.group(0), html,
                          count=1, flags=re.I)
        html = re.sub(r"</head\s*>", lambda match: branding + "\n" + match.group(0),
                      html, count=1, flags=re.I)
        response.set_data(html)
        return response
