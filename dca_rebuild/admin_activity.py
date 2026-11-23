"""Private recent-activity feed for The LiteFeet Vault admin overview.

Only records with reliable database timestamps appear. A submission's current
status is displayed separately from the event that was actually timestamped.
This is not a replacement for a full, append-only audit log.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import abort, render_template, request, url_for

from dca_rebuild.models import (
    BetaChangelog, BetaFeedback, DCANewCategorySuggestion,
    DCANominationSubmission, DCANominee, LFAArchiveSubmission,
    LockInCardRequest, VaultArchiveVerification, VaultDevelopmentFeedback,
    VaultDevelopmentItem, VaultGatheringSubmission, WorldRecordInterest,
)

AREAS = ("all", "awards", "events", "archive", "feedback", "development", "community")
PERIODS = ("7", "30", "90", "all")
EASTERN = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class ActivitySource:
    area: str
    label: str
    model: object
    title_field: str | None
    time_field: str
    action: str
    status_field: str | None
    endpoint: str
    route_param: str | None = None


# Each event is backed by an actual timestamp. No made-up approval dates,
# anonymous visitor identities, emails, or IP-derived details are surfaced.
SOURCES = (
    ActivitySource("events", "Event", VaultGatheringSubmission, "title",
                   "created_at", "Submitted", "status",
                   "admin_vault_gathering_edit", "submission_id"),
    ActivitySource("events", "Event", VaultGatheringSubmission, "title",
                   "reviewed_at", "Reviewed", "status",
                   "admin_vault_gathering_edit", "submission_id"),
    ActivitySource("awards", "DCA nominee", DCANominee, "name",
                   "created_at", "Submitted", "moderation_status",
                   "admin_dca_nominations"),
    ActivitySource("awards", "DCA nominee", DCANominee, "name",
                   "reviewed_at", "Reviewed", "moderation_status",
                   "admin_dca_nominations"),
    ActivitySource("awards", "DCA category", DCANewCategorySuggestion, "category_name",
                   "created_at", "Suggested", "moderation_status", "admin_round1"),
    ActivitySource("awards", "DCA nomination", DCANominationSubmission, None,
                   "submitted_at", "Received", None, "admin_dca_nominations"),
    ActivitySource("awards", "LiteFeet Award", LFAArchiveSubmission, "winner_name",
                   "created_at", "Submitted", "status", "admin_lfa_submissions"),
    ActivitySource("archive", "Archive response", VaultArchiveVerification, "record_slug",
                   "created_at", "Submitted", "moderation_status",
                   "admin_vault_auxiliary_review"),
    ActivitySource("archive", "Lock In card", LockInCardRequest, "card_name",
                   "created_at", "Suggested", "status",
                   "admin_vault_auxiliary_review"),
    ActivitySource("archive", "Lock In card", LockInCardRequest, "card_name",
                   "reviewed_at", "Reviewed", "status",
                   "admin_vault_auxiliary_review"),
    ActivitySource("feedback", "Beta feedback", BetaFeedback, None,
                   "created_at", "Received", "status", "admin_beta_feedback"),
    ActivitySource("feedback", "Website feedback", VaultDevelopmentFeedback, "title",
                   "created_at", "Received", "status", "admin_vault_development"),
    ActivitySource("feedback", "Website feedback", VaultDevelopmentFeedback, "title",
                   "reviewed_at", "Reviewed", "status", "admin_vault_development"),
    ActivitySource("development", "Development task", VaultDevelopmentItem, "title",
                   "updated_at", "Created / updated", "status",
                   "admin_vault_development"),
    ActivitySource("development", "Changelog", BetaChangelog, "title",
                   "created_at", "Entry created", None, "admin_beta_changelog"),
    ActivitySource("community", "World Record interest", WorldRecordInterest, None,
                   "created_at", "Received", "status", "admin_world_record"),
)


def _label_status(value):
    if value is None:
        return ""
    return str(value).replace("_", " ").strip().title()


def _fetch_activity(db, area="all", period="30", page=1, size=20):
    """Return one globally date-sorted page without exposing private identifiers."""
    if area not in AREAS or period not in PERIODS or page < 1 or page > 100:
        abort(400)
    cutoff = None if period == "all" else datetime.utcnow() - timedelta(days=int(period))
    sample_size = page * size + 1
    candidates = []

    for source in SOURCES:
        if area != "all" and area != source.area:
            continue
        date_column = getattr(source.model, source.time_field)
        query = db.query(source.model).filter(date_column.isnot(None))
        if cutoff is not None:
            query = query.filter(date_column >= cutoff)
        records = query.order_by(date_column.desc(), source.model.id.desc()).limit(sample_size).all()
        for record in records:
            stamped = getattr(record, source.time_field)
            if not isinstance(stamped, datetime):
                continue
            # DB dates are UTC; convert for the New York-based admin interface.
            utc = stamped.replace(tzinfo=timezone.utc) if stamped.tzinfo is None else stamped.astimezone(timezone.utc)
            eastern = utc.astimezone(EASTERN)
            title = getattr(record, source.title_field, None) if source.title_field else None
            title = str(title).strip()[:120] if title else source.label
            kwargs = {source.route_param: record.id} if source.route_param else {}
            candidates.append({
                "area": source.area,
                "label": source.label,
                "title": title,
                "action": source.action,
                "status": _label_status(getattr(record, source.status_field, None)) if source.status_field else "",
                "at": eastern.strftime("%m-%d-%Y · %-I:%M %p"),
                "iso_at": utc.isoformat(),
                "url": url_for(source.endpoint, **kwargs),
                "_sort": (utc, source.area, source.label, record.id, source.action),
            })

    candidates.sort(key=lambda item: item["_sort"], reverse=True)
    start, stop = (page - 1) * size, page * size
    rows = candidates[start:stop]
    for row in rows:
        del row["_sort"]
    return rows, len(candidates) > stop


def install_admin_activity(app, ns):
    admin_required = ns["admin_login_required"]

    @app.context_processor
    def inject_admin_activity_preview():
        if request.endpoint != "admin_dashboard":
            return {}
        with ns["SessionLocal"]() as db:
            rows, _ = _fetch_activity(db, size=8)
        return {"recent_activity_rows": rows}

    @app.get("/admin/activity", endpoint="admin_vault_activity")
    @admin_required
    def admin_activity():
        area = request.args.get("area", "all")
        period = request.args.get("period", "30")
        try:
            page = int(request.args.get("page", "1"))
        except (TypeError, ValueError):
            abort(400)
        with ns["SessionLocal"]() as db:
            rows, has_more = _fetch_activity(db, area, period, page, 20)
        return render_template(
            "admin_workspace_activity.html", recent_activity_rows=rows,
            area=area, period=period, page=page, has_more=has_more, areas=AREAS,
            periods=PERIODS,
        )
