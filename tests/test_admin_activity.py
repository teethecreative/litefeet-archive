"""Recent activity feed uses real timestamps and remains admin-only."""
from datetime import datetime, timedelta

from dca_rebuild.models import (
    BetaFeedback, VaultDevelopmentItem, VaultDevelopmentFeedback,
    VaultGatheringSubmission, DCANominee, DCANominationSubmission,
)


def _admin(client):
    with client.session_transaction() as session:
        session["ledger_admin_authenticated"] = True


def test_recent_activity_private_and_linked_from_overview(website, database):
    with database[1].begin() as db:
        db.add(VaultGatheringSubmission(
            title="Dance Lab", gathering_type="lab", start_date="2026-12-05",
            hosts="Studio", address="Example venue", status="approved",
            created_at=datetime.utcnow() - timedelta(hours=3),
            reviewed_at=datetime.utcnow() - timedelta(hours=1)))
        db.add(VaultDevelopmentItem(
            title="Fix search navigation", status="active", area="site",
            updated_at=datetime.utcnow() - timedelta(hours=2)))
    client = website.test_client()
    assert client.get("/admin/activity").status_code in (302, 303, 401, 403)
    _admin(client)
    overview = client.get("/admin").get_data(as_text=True)
    assert "Activity" in overview and "LAST 30 DAYS" in overview
    assert "Dance Lab" in overview
    page = client.get("/admin/activity").get_data(as_text=True)
    assert page.index("Reviewed") < page.index("Fix search navigation") < page.index("Submitted")
    assert "Approved" in page
    assert "View full activity" in overview


def test_activity_filters_and_private_contact_details(website, database):
    now = datetime.utcnow()
    with database[1].begin() as db:
        db.add(BetaFeedback(email="private@example.org", message="Private message",
                            status="new", created_at=now - timedelta(hours=2)))
        db.add(VaultDevelopmentFeedback(
            title="Improve archive search", details="Please add a filter",
            contact_email="secret@example.org", status="new",
            created_at=now - timedelta(days=15)))
        db.add(VaultDevelopmentItem(
            title="Old archive task", area="archive", status="planned",
            updated_at=now - timedelta(days=100)))
    client = website.test_client()
    _admin(client)
    recent = client.get("/admin/activity?area=feedback&period=7").get_data(as_text=True)
    assert "Beta feedback" in recent
    assert "Improve archive search" not in recent
    assert "Private message" not in recent
    assert "private@example.org" not in recent
    assert "secret@example.org" not in recent
    older = client.get("/admin/activity?area=development&period=all").get_data(as_text=True)
    assert "Old archive task" in older
    assert client.get("/admin/activity?period=banana").status_code == 400
    assert client.get("/admin/activity?area=banana").status_code == 400
    assert client.get("/admin/activity?page=0").status_code == 400

def test_nomination_activity_displays_nominee_name_and_category(website, database):
    edition_id = database[2]
    now = datetime.utcnow()
    with database[1].begin() as db:
        from dca_rebuild.models import DCACategory
        category = db.query(DCACategory).filter_by(
            edition_id=edition_id, name="Category 1"
        ).one()
        nominee = DCANominee(
            edition_id=edition_id,
            category_id=category.id,
            name="Example LiteFeet Dancer",
            normalized_name="example litefeet dancer",
            moderation_status="approved",
            created_at=now - timedelta(hours=3),
        )
        db.add(nominee)
        db.flush()
        db.add(DCANominationSubmission(
            edition_id=edition_id, nominee_id=nominee.id,
            submitter_hash="test-only-nomination-hash",
            submitted_at=now - timedelta(minutes=5),
        ))
    client = website.test_client()
    _admin(client)
    overview = client.get("/admin").get_data(as_text=True)
    assert "<strong>Example LiteFeet Dancer</strong><small>Category 1</small>" in overview
    assert "<strong>DCA nomination</strong>" not in overview
    history = client.get("/admin/activity?area=awards&period=7").get_data(as_text=True)
    assert "<strong>Example LiteFeet Dancer</strong><small>Category 1</small>" in history
    assert "Received" in history


def test_overview_is_short_cross_section_but_history_remains_complete(website, database):
    """A flood of DCA entries must not crowd out recent activity from other sections."""
    from dca_rebuild.models import VaultArchiveContribution
    from dca_rebuild.profile_claims import VaultProfileClaim
    from dca_rebuild.admin_activity import _fetch_activity
    now = datetime.utcnow()
    with database[1].begin() as db:
        for index in range(9):
            db.add(VaultDevelopmentItem(
                title=f"Development update {index}", area="site", status="active",
                updated_at=now - timedelta(minutes=index)))
        db.add(VaultArchiveContribution(
            contribution_type="historical_event", title="Historic dance event",
            description="Archive contribution", contact_email="private@example.org",
            created_at=now - timedelta(hours=2)))
        db.add(VaultProfileClaim(
            profile_href="/people/example", claimant_hash="test-hash",
            masked_email="te***@example.org", relationship="self",
            explanation="My profile", created_at=now - timedelta(hours=3)))
    client = website.test_client()
    _admin(client)
    overview = client.get("/admin").get_data(as_text=True)
    assert overview.count('class="lfv-admin-overview__entry"') <= 5
    assert "Historic dance event" in overview
    assert "/people/example" in overview
    history = client.get("/admin/activity?period=30").get_data(as_text=True)
    assert "Development update 8" in history
    assert "Historic dance event" in history
    assert "/people/example" in history
    with database[1]() as db:
        rows, _ = _fetch_activity(db, period="30", size=20)
    assert len(rows) >= 11
    assert all(rows[i]["iso_at"] >= rows[i+1]["iso_at"] for i in range(len(rows)-1))
