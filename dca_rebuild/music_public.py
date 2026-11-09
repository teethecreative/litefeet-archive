"""Public Music route for the deployed Vault application.

Read-only access to existing published media_items where the current database
contains the legacy music table. Do not create/migrate/delete historical data.
"""
from flask import render_template, request, abort
from datetime import datetime, date
import re
from sqlalchemy import inspect, text
from dca_rebuild.archive_catalog import all_records, find_record
from dca_rebuild.music_batch_catalog import combined_releases, batch_record, all_music_catalog
from dca_rebuild.music_presentation import with_release_display, duplicate_release_candidates

def full_date(value):
    """Render stored release dates with spelled-out months; never invent precision."""
    if not value:
        return "Date unknown"
    if isinstance(value, (datetime, date)):
        return f"{value.strftime('%B')} {value.day}, {value.year}"
    raw = str(value).strip()
    for pattern in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            value = datetime.strptime(raw[:10] if pattern == "%Y-%m-%d" else raw, pattern)
            return f"{value.strftime('%B')} {value.day}, {value.year}"
        except ValueError:
            pass
    if re.fullmatch(r"\d{4}-\d{2}", raw):
        try:
            return datetime.strptime(raw, "%Y-%m").strftime("%B %Y")
        except ValueError:
            pass
    if re.fullmatch(r"\d{4}", raw):
        return raw
    return "Date unknown"


def music_duration(item):
    """Only display known durations; never infer them from upload date or title."""
    value = item.get("duration_seconds") or item.get("duration") or item.get("runtime")
    if not value:
        return "—"
    if isinstance(value, (int, float)) or str(value).isdigit():
        total = int(float(value))
        if total < 0:
            return "—"
        return f"{total // 60}:{total % 60:02d}"
    raw = str(value).strip()
    if re.fullmatch(r"\d{1,2}:\d{2}(?::\d{2})?", raw):
        return raw
    return "—"


def install_music_public(app, engine):
    def music_rows():
        metadata = inspect(engine)
        if not metadata.has_table("media_items"):
            return []
        required = {"id", "title", "media_type", "status", "release_date"}
        if not required.issubset({column["name"] for column in metadata.get_columns("media_items")}):
            app.logger.warning("Existing media_items schema is not compatible with music timeline")
            return []
        with engine.connect() as connection:
            return [dict(row) for row in connection.execute(text(
                """SELECT * FROM media_items
                   WHERE media_type = 'music_release' AND status = 'Published'
                   ORDER BY CASE WHEN release_date IS NULL OR release_date = ''
                                 THEN '0000' ELSE release_date END DESC, id DESC"""
            )).mappings()]

    # SEO reads the same published records as Release Radar, without writing to them.
    app.extensions["vault_published_music_rows"] = music_rows

    @app.get("/litefeet-music", endpoint="vault_music_public")
    def vault_music_public():
        search = (request.args.get("q") or "").strip().casefold()[:120]
        releases = combined_releases(music_rows(), full_date, music_duration)
        from dca_rebuild.public_urls import music_href
        for row in releases:
            row["public_href"] = music_href(row, releases)
        if search:
            releases = [row for row in releases if search in " ".join(
                str(row.get(k) or "") for k in
                ("title", "artist", "artist_or_creator", "producer", "producer_name",
                 "description", "project_title", "record_type")
            ).casefold()]
        return render_template("music_timeline.html",
                               releases=[with_release_display(row) for row in releases],
                               search=search)

    @app.get("/litefeet-music/release/<int:item_id>", endpoint="vault_music_release")
    def vault_music_release(item_id):
        item = next((row for row in music_rows() if row["id"] == item_id), None)
        if item is None:
            abort(404)
        return render_template("music_release_public.html", item=with_release_display(dict(
            item, date_label=full_date(item.get("release_date")),
            duration_label=music_duration(item))))

    @app.get("/litefeet-music/catalog/<kind>/<catalog_id>", endpoint="vault_music_catalog_record")
    def vault_music_catalog_record(kind, catalog_id):
        if kind not in ("track", "project"):
            abort(404)
        item = batch_record(kind, catalog_id)
        if item is None:
            abort(404)
        tracks = ([dict(row, record_href="/litefeet-music/catalog/track/" + row["catalog_id"])
                   for row in all_music_catalog()
                   if row["kind"] == "track" and row.get("project_id") == catalog_id]
                  if kind == "project" else [])
        tracks.sort(key=lambda row: int(row.get("track_number") or 999))
        return render_template("music_release_public.html", item=with_release_display(dict(
            item, date_label=(full_date(item.get("release_date"))
                 if item.get("release_date") else item.get("release_year") or "Date unknown"),
            duration_label=music_duration(item))), project_tracks=tracks)
    
    @app.get("/media", endpoint="vault_media_public")
    def vault_media_public():
        # This section is intentionally unpublished until editorial launch.
        abort(404)

    @app.get("/litefeet-music/history/<slug>", endpoint="vault_music_history")
    def vault_music_history(slug):
        record = find_record(slug)
        if not record or record.get("collection") != "music":
            abort(404)
        # The canonical public archive detail contains research sources.
        from flask import redirect
        return redirect("/archive/records/" + slug, code=302)
