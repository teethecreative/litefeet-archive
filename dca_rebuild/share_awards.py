"""Public, data-driven Dancer's Choice Awards share graphics.

No uploads, stored user images, supporter emails, or database writes. All names
and counts come from the same public aggregates as the nomination standings.
"""
from functools import lru_cache
from io import BytesIO
from math import ceil
from zipfile import ZipFile, ZIP_DEFLATED

from flask import Response, abort, jsonify, request
from PIL import Image, ImageDraw

from dca_rebuild.models import DCAEdition
from dca_rebuild.phase9e import get_counts, stages_for, writein_category_label
from dca_rebuild.seo import SITE_URL
from dca_rebuild.social_cards import _font, _wrap, render_social_card

FORMATS = ("story", "post")
THEMES = ("light", "dark")
SCOPES = ("awards", "category", "nominees", "nominee")
PER_PAGE = {"story": 10, "post": 5}

# Suggested support messages express the visitor's opinion, not an official finding.
PRESET_REASONS = {
    "impact": "I want to recognize the work and impact this nominee brings to LiteFeet culture.",
    "creativity": "I want to nominate them for the creativity and originality they bring to the culture.",
    "consistency": "I want to recognize their consistency, dedication, and commitment to LiteFeet.",
    "community": "I want to show support for the positive impact they have on the LiteFeet community.",
}
MAX_CUSTOM_REASON = 180


def resolve_reason(mode, custom_text="", *, allow_custom=False):
    """Create an ephemeral supporter message; never write custom text to the database."""
    if mode in (None, "", "none"):
        return "", ""
    if mode in PRESET_REASONS:
        return "Suggested reason", PRESET_REASONS[mode]
    if mode != "custom" or not allow_custom:
        abort(400, description="Invalid reason selection")
    if not isinstance(custom_text, str) or len(custom_text) > MAX_CUSTOM_REASON:
        abort(400, description="Reason must be 180 characters or fewer")
    clean = " ".join(custom_text.split())
    if not clean or len(clean) > MAX_CUSTOM_REASON:
        abort(400, description="Write a short reason for supporting this nominee")
    if any(ord(char) < 32 for char in clean):
        abort(400, description="Reason contains unsupported characters")
    return "Supporter's message", clean



def public_categories():
    """Re-use the nominated categories and existing public pending/approved counts."""
    from dca_rebuild.app import SessionLocal
    db = SessionLocal()
    try:
        edition = db.query(DCAEdition).filter_by(year=2026, is_public=True).first()
        if edition is None:
            return []
        counts, _ = get_counts(db, edition, include_pending=True)
        return [
            {
                "id": category.id, "name": writein_category_label(category.name),
                "nominees": [
                    {"id": n["id"], "name": n["name"], "count": n["count"]}
                    for n in counts.get(category.id, [])
                ],
            }
            for stage, category in stages_for(db, edition)
            if stage.stage in ("top25", "write_in", "qualified")
        ]
    finally:
        db.close()


def select_public(scope, category_id=None, nominee_id=None):
    if scope not in SCOPES:
        abort(404)
    if scope == "awards":
        return {"scope": scope, "category": None, "nominee": None, "nominees": []}
    if not isinstance(category_id, int) or category_id < 1:
        abort(404)
    category = next((c for c in public_categories() if c["id"] == category_id), None)
    if category is None:
        abort(404)
    nominee = None
    if scope == "nominee":
        if not isinstance(nominee_id, int) or nominee_id < 1:
            abort(404)
        nominee = next((n for n in category["nominees"] if n["id"] == nominee_id), None)
        if nominee is None:
            abort(404)
    return {
        "scope": scope, "category": category,
        "nominee": nominee, "nominees": category["nominees"],
    }


def page_count(selection, fmt):
    return max(1, ceil(len(selection["nominees"]) / PER_PAGE[fmt])) if selection["scope"] == "nominees" else 1


def share_url(selection):
    if selection["scope"] == "awards":
        return SITE_URL + "/awards/dancers-choice/2026"
    category = selection["category"]
    url = (SITE_URL + "/awards/dancers-choice/nominations?view=results&category="
           + str(category["id"]))
    if selection["nominee"]:
        url += "&suggestion=" + str(selection["nominee"]["id"])
    return url


def _content(selection):
    scope = selection["scope"]
    category = selection["category"]
    if scope == "awards":
        return ("Dancer's Choice Awards 2026", "Explore the awards and community nominations.")
    if scope == "category":
        return (category["name"], "Explore this award category.")
    if scope == "nominees":
        return (category["name"] + " — Nominees", "Explore the listed nominees in this category.")
    nominee = selection["nominee"]
    return (nominee["name"] + " — " + category["name"], "Explore this nominee and category.")


def _draw(fmt, theme, scope, title, nominee_name, nominee_count, entries, page, total, reason_label="", reason_text=""):
    w, h = 1080, 1920 if fmt == "story" else 1350
    dark = theme == "dark"
    bg = "#071d3b" if dark else "#f8f7f2"
    fg = "#f8f7f2" if dark else "#071d3b"
    subdued = "#c6d2df" if dark else "#394e68"
    gold = "#d9ac47"
    blue = "#143f80"
    img = Image.new("RGB", (w, h), bg)
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, w, 250), fill="#122f58" if dark else "#071d3b")
    draw.rectangle((0, 244, w, 252), fill=gold)
    draw.text((76, 65), "THE LITEFEET VAULT", font=_font(54, True), fill="#ffffff")
    draw.text((78, 147), "DANCER'S CHOICE AWARDS  /  2026", font=_font(31, True), fill=gold)
    draw.text((80, 317), "THE CULTURE DECIDES", font=_font(28, True), fill=gold if dark else blue)
    heading = "DANCER'S CHOICE\nAWARDS 2026" if scope == "awards" else title.upper()
    heading_font_size = 74 if len(heading) < 36 else 64 if len(heading) < 62 else 51
    heading_font = _font(heading_font_size, True)
    lines = (heading.split("\n") if scope == "awards"
             else _wrap(draw, heading, heading_font, 915, 4 if fmt == "story" else 3))
    y = 393
    for line in lines:
        draw.text((76, y), line, font=heading_font, fill=fg)
        y += heading_font_size + 15
    rule_y = y + 20
    draw.rectangle((80, rule_y, 995, rule_y + 7), fill=gold)
    y = rule_y + 53

    if scope == "awards":
        draw.text((80, y), "2026 AWARDS", font=_font(43, True), fill=fg)
        draw.text((80, y + 80), "Explore categories and nominations.", font=_font(31), fill=subdued)
    elif scope == "category":
        draw.text((80, y), "AWARD CATEGORY", font=_font(36, True), fill=subdued)
        draw.text((80, y + 76), "Explore this year's nominees.", font=_font(31), fill=fg)
    elif scope == "nominee":
        # Keep the nominee prominent; reserve a legible area for a visitor's reason.
        draw.text((80, y), "NOMINATE", font=_font(29, True), fill=subdued)
        name_size = 67 if len(nominee_name) < 28 else 53
        name_font = _font(name_size, True)
        cursor = y + 71
        for line in _wrap(draw, nominee_name, name_font, 908, 3):
            draw.text((80, cursor), line, font=name_font, fill=gold if dark else blue)
            cursor += name_size + 14
        draw.text((80, cursor + 11), f"{nominee_count} nomination" + ("" if nominee_count == 1 else "s"),
                  font=_font(29), fill=subdued)
        if reason_text:
            # Feed images are shorter. Shrink the supporter message instead of
            # letting long text cover the footer or falsely appear official.
            footer_limit = h - 260
            box_top = cursor + 87
            available = footer_limit - box_top
            if available > 120:
                draw.rounded_rectangle((76, box_top, 1002, footer_limit), radius=16,
                                       fill="#17365e" if dark else "#e8edeb")
                draw.rectangle((76, box_top, 86, footer_limit), fill=gold)
                draw.text((116, box_top + 25), reason_label.upper(),
                          font=_font(25, True), fill=gold if dark else blue)
                text_lines = []
                message_font = _font(31 if fmt == "story" else 27)
                for line in _wrap(draw, reason_text, message_font, 835, 5 if fmt == "story" else 4):
                    text_lines.append(line)
                line_height = 45 if fmt == "story" else 39
                while (text_lines and len(text_lines) * line_height + 92 > available
                       and message_font.size > 19):
                    message_font = _font(message_font.size - 2)
                    text_lines = _wrap(draw, reason_text, message_font, 835, 5 if fmt == "story" else 4)
                    line_height = message_font.size + 11
                for i, line in enumerate(text_lines):
                    draw.text((116, box_top + 65 + i * line_height),
                              line, font=message_font, fill=fg)
    else:
        draw.text((80, y), "PUBLICLY LISTED NOMINEES", font=_font(29, True), fill=subdued)
        subset = entries[(page - 1) * PER_PAGE[fmt]:page * PER_PAGE[fmt]]
        row_y = y + 87
        if not subset:
            draw.text((80, row_y), "No nominees listed yet.", font=_font(32), fill=fg)
        for index, (name, count) in enumerate(subset, (page - 1) * PER_PAGE[fmt] + 1):
            name_font = _font(31, True)
            max_len = 34
            display = name if len(name) <= max_len else name[:max_len - 1].rstrip() + "…"
            draw.text((80, row_y), f"{index:02d}   {display}", font=name_font, fill=fg)
            draw.text((924, row_y), str(count), font=_font(31, True), fill=gold if dark else blue)
            row_y += 82 if fmt == "story" else 77
        draw.text((80, row_y + 32), f"Nomination totals  •  {page} / {total}",
                  font=_font(26), fill=subdued)

    footer_y = h - 225
    draw.rectangle((0, footer_y, w, h), fill="#122f58" if dark else "#071d3b")
    draw.rectangle((0, footer_y, w, footer_y + 7), fill=gold)
    draw.text((80, footer_y + 55), "EXPLORE THE CULTURE", font=_font(38, True), fill="#ffffff")
    draw.text((80, footer_y + 137), "THELITEFEETVAULT.COM", font=_font(31), fill=gold)
    if total > 1:
        draw.text((888, footer_y + 137), f"{page}/{total}", font=_font(30, True), fill="#ffffff")
    out = BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()


def graphic(fmt, theme, chosen, page=1, reason_mode=None, reason_text="", *, allow_custom=False):
    if fmt not in FORMATS or theme not in THEMES:
        abort(404)
    total = page_count(chosen, fmt)
    if page is None or not 1 <= page <= total:
        abort(404)
    category = chosen["category"]
    nominee = chosen["nominee"]
    title = ("THE CULTURE DECIDES." if not category else category["name"])
    names = tuple((n["name"], n["count"]) for n in chosen["nominees"])
    reason_label, resolved_text = ("", "")
    if chosen["scope"] == "nominee":
        reason_label, resolved_text = resolve_reason(reason_mode, reason_text,
                                                      allow_custom=allow_custom)
    return _draw(fmt, theme, chosen["scope"], title, nominee["name"] if nominee else "",
                 nominee["count"] if nominee else 0, names, page, total,
                 reason_label, resolved_text)


def install_award_sharing(app):
    @app.get("/social/awards/options.json")
    def awards_share_options():
        response = jsonify({"categories": public_categories()})
        response.headers["Cache-Control"] = "public, max-age=60"
        return response

    @app.get("/social/awards/preview/<scope>.png")
    def awards_share_preview(scope):
        chosen = select_public(scope, request.args.get("category", type=int),
                               request.args.get("nominee", type=int))
        title, description = _content(chosen)
        data = render_social_card("page", title, description)
        return Response(data, mimetype="image/png", headers={"Cache-Control": "public, max-age=60"})

    @app.route("/social/awards/<fmt>/<theme>/<scope>.png", methods=["GET", "POST"])
    def awards_share_png(fmt, theme, scope):
        chosen = select_public(scope, request.values.get("category", type=int),
                               request.values.get("nominee", type=int))
        reason_mode = (request.form.get("reason_mode") if request.method == "POST"
                       else request.args.get("reason"))
        # Custom copy is accepted only in POST bodies, never in URLs/logged queries.
        data = graphic(fmt, theme, chosen, request.values.get("page", default=1, type=int),
                       reason_mode, request.form.get("reason_text", ""),
                       allow_custom=request.method == "POST")
        return Response(data, mimetype="image/png",
                        headers={"Cache-Control": "public, max-age=60",
                                 "X-Content-Type-Options": "nosniff"})

    @app.get("/social/awards/bundle.zip")
    def awards_share_bundle():
        fmt, theme = request.args.get("format"), request.args.get("theme")
        if fmt not in FORMATS or theme not in THEMES or request.args.get("scope") != "nominees":
            abort(404)
        chosen = select_public("nominees", request.args.get("category", type=int))
        total = page_count(chosen, fmt)
        buf = BytesIO()
        with ZipFile(buf, "w", compression=ZIP_DEFLATED) as archive:
            for page in range(1, total + 1):
                archive.writestr(f"litefeet-{fmt}-{theme}-{page:02d}.png",
                                 graphic(fmt, theme, chosen, page))
        return Response(buf.getvalue(), mimetype="application/zip",
                        headers={"Content-Disposition": 'attachment; filename="litefeet-awards-nominees.zip"',
                                 "Cache-Control": "no-store"})
