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


@lru_cache(maxsize=256)
def _draw(fmt, theme, scope, title, nominee_name, nominee_count, entries, page, total):
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
        draw.text((80, y), "FEATURED NOMINEE", font=_font(30, True), fill=subdued)
        name_font = _font(72 if len(nominee_name) < 29 else 58, True)
        cursor = y + 78
        for line in _wrap(draw, nominee_name, name_font, 908, 3):
            draw.text((80, cursor), line, font=name_font, fill=gold if dark else blue)
            cursor += (79 if len(nominee_name) < 29 else 65)
        draw.text((80, cursor + 25), f"{nominee_count} nomination" + ("" if nominee_count == 1 else "s"),
                  font=_font(34), fill=subdued)
        draw.text((80, cursor + 105), "VIEW THIS NOMINEE ON THE VAULT", font=_font(28, True), fill=fg)
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


def graphic(fmt, theme, chosen, page=1):
    if fmt not in FORMATS or theme not in THEMES:
        abort(404)
    total = page_count(chosen, fmt)
    if page is None or not 1 <= page <= total:
        abort(404)
    category = chosen["category"]
    nominee = chosen["nominee"]
    title = ("THE CULTURE DECIDES." if not category else category["name"])
    names = tuple((n["name"], n["count"]) for n in chosen["nominees"])
    return _draw(fmt, theme, chosen["scope"], title, nominee["name"] if nominee else "",
                 nominee["count"] if nominee else 0, names, page, total)


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

    @app.get("/social/awards/<fmt>/<theme>/<scope>.png")
    def awards_share_png(fmt, theme, scope):
        chosen = select_public(scope, request.args.get("category", type=int),
                               request.args.get("nominee", type=int))
        data = graphic(fmt, theme, chosen, request.args.get("page", default=1, type=int))
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
