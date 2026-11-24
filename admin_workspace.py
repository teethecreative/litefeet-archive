"""Shared admin review workspace; existing moderation endpoints remain authoritative."""
from flask import request, render_template, redirect, url_for, abort, session
from sqlalchemy import inspect, text

# table, status field, pending states, display fields, existing screen, action endpoint, id parameter, choices
QUEUES = {
    "submissions": ("Submissions","submissions","review_status",("Pending Review","Needs Verification","Needs Review","Disputed"),("title","related_to"),"/admin/submissions","update_submission_status","submission_id",("Verified","Rejected")),
    "claims": ("Profile claims","profile_claims","claim_status",("Pending Review","Needs Review","Needs Follow-up"),("claimant_name","claim_reason"),"/admin/phase2?section=claims","admin_phase2_profile_claim_status","claim_id",("Rejected",)),
    "edits": ("Profile edits","profile_edit_logs","edit_status",("Logged","Needs Follow-up","Pending Review"),("edit_action","profile_id"),"/admin/profile-corrections",None,None,()),
    "links": ("Profile links","profile_account_links","status",("pending",),("profile_type","profile_id"),"/admin/profile-links","admin_update_profile_link_status","link_id",("approved","rejected")),
    "visibility": ("Visibility requests","profile_visibility_requests","public_profile_status",("pending",),("field_name","reason"),"/admin/profile-visibility-requests",None,None,()),
    "roles": ("Role requests","role_requests","status",("Pending","Pending Review"),("requested_role","reason"),"/admin/role-requests","update_role_request_status","request_id",("Approved","Rejected")),
    "perspectives": ("Community perspectives","community_perspectives","perspective_status",("Pending Review","Needs Review","Needs Verification","Debated"),("perspective_text",),"/admin/phase2?section=perspectives",None,None,()),
    "battles": ("Battle records","battle_records","review_status",("Pending Review","Needs Review","Needs Verification","Disputed"),("competitor_one","competitor_two"),"/admin/phase2?section=battles",None,None,()),
    "calendar": ("Events","calendar_item_metadata","review_status",("Pending Review","Needs Review","Needs Verification","Disputed"),("venue_name","calendar_type"),"/admin/calendar-review",None,None,()),
    "music": ("Music feedback","music_feedback","feedback_status",("New","Needs Follow-up","Needs Source"),("feedback","media_item_id"),"/admin/music-feedback",None,None,()),
    "ask": ("Ask feedback","ask_feedback","feedback_status",("New","Needs Fix","Needs Context"),("feedback_text",),"/admin/ask-feedback",None,None,()),
    "suggestions": ("Dancer suggestions","dancer_suggestions","status",("Pending Review","Needs Review"),("suggestion_text",),"/admin/dancer-feedback","update_dancer_suggestion_status","suggestion_id",("Approved","Rejected")),
    "flowers": ("Flowers","dancer_flowers","status",("Pending Review","Needs Review"),("flower_text",),"/admin/dancer-feedback","update_dancer_flower_status","flower_id",("Approved","Rejected")),
    "awards": ("Award records","award_records","review_status",("Pending Review","Needs Review","Needs Verification","Disputed"),("category","winner_name","nominee_name"),"/admin/records/awards",None,None,()),
    "teams": ("Team records","team_records","review_status",("Pending Review","Needs Review","Needs Verification","Disputed"),("team_name","founder_names"),"/admin/records/teams",None,None,()),
}
FIELDS = {
    "awards": ("award_year","organizer","award_show","category","nominee_name","winner_name","result_status","source_url","notes"),
    "teams": ("team_name","aka_names","founder_names","current_leads","borough_scene","era","status","known_for","bio","source_url"),
}
STATUSES = ("Pending Review","Needs Review","Needs Verification","Community Supported","Verified","Disputed","Rejected")

def register_admin_workspace(app, engine, is_admin):
    def guard():
        if not session.get("admin_logged_in") or not is_admin():
            abort(403)

    @app.route("/admin/review")
    def vault_review():
        guard()
        kind = request.args.get("type","all")
        if kind != "all" and kind not in QUEUES:
            abort(404)
        q = request.args.get("q","").strip().casefold()
        rows, unavailable, counts = [], [], {}
        for key, spec in QUEUES.items():
            label, table, status, pending, fields, screen, endpoint, param, choices = spec
            try:
                columns = {c["name"] for c in inspect(engine).get_columns(table)}
                if not {"id",status}.issubset(columns):
                    raise ValueError("Review fields unavailable")
                params = {"default":pending[0]}
                marks = []
                for i, value in enumerate(pending):
                    name = "p"+str(i)
                    params[name] = value.lower()
                    marks.append(":"+name)
                where = "LOWER(COALESCE("+status+", :default)) IN ("+",".join(marks)+")"
                with engine.connect() as conn:
                    counts[key] = conn.execute(text("SELECT COUNT(*) FROM "+table+" WHERE "+where),params).scalar()
                    if kind not in ("all",key):
                        continue
                    records = conn.execute(text("SELECT * FROM "+table+" WHERE "+where+" ORDER BY id DESC LIMIT 250"),params).mappings().all()
                for rec in records:
                    title = " · ".join(str(rec.get(f)) for f in fields if rec.get(f)) or "#"+str(rec["id"])
                    if q and q not in title.casefold():
                        continue
                    action = url_for(endpoint, **{param:rec["id"]}) if endpoint else None
                    approve_claim = url_for("admin_phase4_approve_profile_claim_link",claim_id=rec["id"]) if key=="claims" else None
                    rows.append(dict(kind=key,label=label,id=rec["id"],title=title,status=rec.get(status) or pending[0],date=str(rec.get("created_at") or rec.get("requested_at") or ""),screen=screen,action=action,field=status,choices=choices,approve_claim=approve_claim))
            except Exception:
                app.logger.exception("Review queue unavailable: %s",key)
                unavailable.append(label)
        rows.sort(key=lambda r:r["date"],reverse=True)
        return render_template("admin_unified_review.html",rows=rows,queues=QUEUES,counts=counts,kind=kind,q=q,unavailable=unavailable)

    @app.route("/admin/records/<kind>", methods=["GET","POST"])
    def vault_records(kind):
        guard()
        if kind not in FIELDS:
            abort(404)
        label, table, status, pending, _, _, _, _, _ = QUEUES[kind]
        fields = FIELDS[kind]
        if request.method=="POST":
            record_id = request.form.get("id",type=int)
            new_status = request.form.get("review_status","")
            if not record_id or new_status not in STATUSES:
                abort(400)
            values = {"id":record_id,"review_status":new_status}
            updates = ["review_status=:review_status"]
            if request.form.get("action")=="edit":
                for field in fields:
                    if field in request.form:
                        values[field] = request.form[field].strip()
                        updates.append(field+"=:"+field)
                required = "category" if kind=="awards" else "team_name"
                if not values.get(required):
                    abort(400)
            with engine.begin() as conn:
                conn.execute(text("UPDATE "+table+" SET "+",".join(updates)+" WHERE id=:id"),values)
            return redirect(url_for("vault_records",kind=kind,q=request.form.get("q",""),page=request.form.get("page",1)))
        q = request.args.get("q","").strip()
        page = max(1,request.args.get("page",1,type=int))
        search = " OR ".join("LOWER(COALESCE("+field+",'')) LIKE :q" for field in fields)
        where = " WHERE ("+search+")" if q else ""
        params = {"q":"%"+q.lower()+"%","offset":(page-1)*25}
        with engine.connect() as conn:
            total = conn.execute(text("SELECT COUNT(*) FROM "+table+where),params).scalar()
            rows = conn.execute(text("SELECT * FROM "+table+where+" ORDER BY id DESC LIMIT 25 OFFSET :offset"),params).mappings().all()
        return render_template("admin_record_manager.html",kind=kind,label=label,rows=rows,fields=fields,statuses=STATUSES,q=q,page=page,total=total)

    @app.after_request
    def return_to_review(response):
        # Only honor a fixed internal destination on successful existing POST redirects.
        if request.method=="POST" and request.path.startswith("/admin/") and request.form.get("_vault_review")=="1" and response.status_code in (302,303) and session.get("admin_logged_in"):
            target = request.form.get("_queue_type","all")
            if target != "all" and target not in QUEUES:
                target = "all"
            if response.headers.get("Location","").startswith("/admin/") and not response.headers.get("Location","").startswith("/admin/login"):
                response.headers["Location"] = url_for("vault_review",type=target,q=request.form.get("_queue_q",""))
        return response
