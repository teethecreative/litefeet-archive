"""Public Music route for the deployed Vault application.

Read-only access to existing published media_items where the current database
contains the legacy music table. Do not create/migrate/delete historical data.
"""
from flask import render_template, request, abort
from sqlalchemy import inspect, text
from dca_rebuild.archive_catalog import all_records, find_record

def install_music_public(app, engine):
    def music_rows():
        if not inspect(engine).has_table("media_items"):
            return []
        with engine.connect() as connection:
            return [dict(row) for row in connection.execute(text(
                """SELECT * FROM media_items
                   WHERE media_type = 'music_release' AND status = 'Published'
                   ORDER BY CASE WHEN release_date IS NULL OR release_date = ''
                                 THEN '0000' ELSE release_date END DESC, id DESC"""
            )).mappings()]

    def history_rows():
        return [record for record in all_records()
                if record.get("collection") == "music"
                and record.get("source_kind") == "research"]

    @app.get("/litefeet-music", endpoint="vault_music_public")
    def vault_music_public():
        search = (request.args.get("q") or "").strip().casefold()[:120]
        releases = music_rows()
        if search:
            releases = [row for row in releases if search in " ".join(
                str(row.get(k) or "") for k in
                ("title", "artist", "artist_or_creator", "producer", "producer_name", "description")
            ).casefold()]
        return render_template("music_timeline.html", releases=releases,
                               history=history_rows(), search=search)

    @app.get("/litefeet-music/release/<int:item_id>", endpoint="vault_music_release")
    def vault_music_release(item_id):
        item = next((row for row in music_rows() if row["id"] == item_id), None)
        if item is None:
            abort(404)
        return render_template("music_release_public.html", item=item)

    @app.get("/litefeet-music/history/<slug>", endpoint="vault_music_history")
    def vault_music_history(slug):
        record = find_record(slug)
        if not record or record.get("collection") != "music":
            abort(404)
        # The canonical public archive detail contains research sources.
        from flask import redirect
        return redirect("/archive/records/" + slug, code=302)
