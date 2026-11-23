"""Private recent-activity feed for The LiteFeet Vault admin overview.

Only records with reliable database timestamps appear. A submission's current
status is displayed separately from the event that was actually timestamped.
This is not a replacement for a full, append-only audit log.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import abort, render_template, request, url_for

from dca_rebuild.profile_wall import (VaultProfileWallPost, VaultProfileWallDecision,
                                      VaultProfileWallOwnerAudit)
from dca_rebuild.profile_claims import VaultProfileClaim

from dca_rebuild.models import (
    BetaChangelog, BetaFeedback, DCANewCategorySuggestion,
    DCANominationSubmission, DCANominee, DCACategory, LFAArchiveSubmission,
    LockInCardRequest, VaultArchiveVerification, VaultDevelopmentFeedback,
    VaultDevelopmentItem, VaultGatheringSubmission, WorldRecordInterest, VaultArchiveContribution,
    DCACategorySuggestionSubmission, DCACategoryBallotSubmission, DCAReturningCategoryReview,
    LFARecord, NewsletterSubscriber, VaultGatheringReviewHistory,
    VaultGatheringOccurrenceOverride, VaultArchiveContributionReview,
    VaultBattleOutcomeHistory, VaultBattleVote, VaultHostAccount,
    VaultHostInvitation, VaultHostBattleAudit,
)

AREAS = ("all", "awards", "events", "archive", "people", "hosts", "feedback", "development", "community")
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
    ActivitySource("archive", "Archive submission", VaultArchiveContribution, "title",
                   "created_at", "Submitted", "status", "admin_archive_contributions"),
    ActivitySource("archive", "Archive submission", VaultArchiveContribution, "title",
                   "reviewed_at", "Reviewed", "status", "admin_archive_contributions"),
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
    ActivitySource("community", "Profile Wall", VaultProfileWallPost, "author_name",
                   "created_at", "Submitted", "status", "admin_profile_walls"),
    ActivitySource("community", "Profile Wall", VaultProfileWallPost, "author_name",
                   "resolved_at", "Resolved", "status", "admin_profile_walls"),
    # Other timestamped activity across the Vault, not just award nominations.
    ActivitySource("awards", "DCA category survey", DCACategorySuggestionSubmission, None,
                   "submitted_at", "Received", None, "admin_round1"),
    ActivitySource("awards", "DCA category ballot", DCACategoryBallotSubmission, None,
                   "submitted_at", "Received", None, "admin_round1"),
    ActivitySource("awards", "DCA category review", DCAReturningCategoryReview, "name_override",
                   "updated_at", "Updated", "status", "admin_dca_workspace"),
    ActivitySource("awards", "LiteFeet Award record", LFARecord, "person_name",
                   "created_at", "Recorded", None, "admin_lfa_records"),
    ActivitySource("events", "Event review", VaultGatheringReviewHistory, None,
                   "created_at", "Updated", None, "admin_vault_gatherings"),
    ActivitySource("events", "Event schedule", VaultGatheringOccurrenceOverride, None,
                   "updated_at", "Updated", None, "admin_vault_gatherings"),
    ActivitySource("archive", "Archive review", VaultArchiveContributionReview, None,
                   "created_at", "Reviewed", None, "admin_archive_contributions"),
    ActivitySource("archive", "Battle result", VaultBattleOutcomeHistory, "event_slug",
                   "updated_at", "Updated", None, "vault_admin_hosts"),
    ActivitySource("community", "Battle poll", VaultBattleVote, None,
                   "created_at", "Voted", None, "vault_admin_hosts"),
    ActivitySource("people", "Profile claim", VaultProfileClaim, "profile_href",
                   "created_at", "Submitted", "status", "admin_profile_claims"),
    ActivitySource("people", "Profile claim", VaultProfileClaim, "profile_href",
                   "resolved_at", "Reviewed", "status", "admin_profile_claims"),
    ActivitySource("people", "Wall moderation", VaultProfileWallDecision, None,
                   "created_at", "Resolved", None, "admin_profile_walls"),
    ActivitySource("people", "Wall owner access", VaultProfileWallOwnerAudit, "profile_href",
                   "created_at", "Updated", None, "admin_profile_walls"),
    ActivitySource("hosts", "Event host", VaultHostAccount, "display_name",
                   "created_at", "Activated", None, "vault_admin_hosts"),
    ActivitySource("hosts", "Host invitation", VaultHostInvitation, "host_key",
                   "created_at", "Invited", "status", "vault_admin_hosts"),
    ActivitySource("hosts", "Host invitation", VaultHostInvitation, "host_key",
                   "claimed_at", "Claimed", "status", "vault_admin_hosts"),
    ActivitySource("hosts", "Host battle update", VaultHostBattleAudit, "event_slug",
                   "created_at", "Updated", None, "vault_admin_hosts"),
    ActivitySource("community", "Newsletter", NewsletterSubscriber, None,
                   "subscribed_at", "Subscribed", None, "admin_analytics"),
    ActivitySource("community", "Newsletter", NewsletterSubscriber, None,
                   "unsubscribed_at", "Unsubscribed", None, "admin_analytics"),
)


def _label_status(value):
    if value is None:
        return ""
    return str(value).replace("_", " ").strip().title()


def _fetch_activity(db, area="all", period="30", page=1, size=20, diverse_preview=False):
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

        # Resolve the submitted nominee and category in one query instead of
        # leaving each nomination activity row with a generic title.
        nomination_details = {}
        if source.model is DCANominationSubmission and records:
            nominee_ids = {record.nominee_id for record in records}
            nomination_details = {
                nominee_id: (nominee_name, category_name)
                for nominee_id, nominee_name, category_name in (
                    db.query(DCANominee.id, DCANominee.name, DCACategory.name)
                    .outerjoin(DCACategory, DCANominee.category_id == DCACategory.id)
                    .filter(DCANominee.id.in_(nominee_ids))
                    .all()
                )
            }

        for record in records:
            stamped = getattr(record, source.time_field)
            if not isinstance(stamped, datetime):
                continue
            # DB dates are UTC; convert for the New York-based admin interface.
            utc = stamped.replace(tzinfo=timezone.utc) if stamped.tzinfo is None else stamped.astimezone(timezone.utc)
            eastern = utc.astimezone(EASTERN)
            title = getattr(record, source.title_field, None) if source.title_field else None
            title = str(title).strip()[:120] if title else source.label
            subtitle = None
            if source.model is DCANominationSubmission:
                nominee_name, category_name = nomination_details.get(record.nominee_id, (None, None))
                if nominee_name and str(nominee_name).strip():
                    title = str(nominee_name).strip()[:120]
                if category_name and str(category_name).strip():
                    subtitle = str(category_name).strip()[:120]
            if source.model is VaultProfileWallPost:
                subtitle = (record.profile_href + (" · Resolved by " + record.resolved_by
                          if source.action == "Resolved" and record.resolved_by else ""))[:180]
            kwargs = {source.route_param: record.id} if source.route_param else {}
            candidates.append({
                "area": source.area,
                "label": source.label,
                "title": title,
                "subtitle": subtitle,
                "action": source.action,
                "status": _label_status(getattr(record, source.status_field, None)) if source.status_field else "",
                "at": eastern.strftime("%m-%d-%Y · %-I:%M %p"),
                "iso_at": utc.isoformat(),
                "url": url_for(source.endpoint, **kwargs),
                "_sort": (utc, source.area, source.label, record.id, source.action),
            })

    candidates.sort(key=lambda item: item["_sort"], reverse=True)
    if diverse_preview:
        # The Overview is a cross-section, not a flood of one category.
        # Newest item per active area first; then fill by timestamp.
        # The full history stays strictly chronological.
        selected, seen_areas = [], set()
        for item in candidates:
            if item["area"] not in seen_areas:
                selected.append(item)
                seen_areas.add(item["area"])
                if len(selected) == size:
                    break
        if len(selected) < size:
            chosen = {id(item) for item in selected}
            for item in candidates:
                if id(item) not in chosen:
                    selected.append(item)
                    if len(selected) == size:
                        break
        rows = sorted(selected, key=lambda item: item["_sort"], reverse=True)
        for row in rows:
            del row["_sort"]
        return rows, False
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
            rows, _ = _fetch_activity(db, size=5, diverse_preview=True)
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
