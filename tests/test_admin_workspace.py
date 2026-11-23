"""Admin Console v2 workstream: unified queue, development, and private feedback."""
from datetime import datetime, timedelta
from dca_rebuild.models import (
    VaultGatheringSubmission, VaultDevelopmentItem, VaultDevelopmentFeedback,
    VaultArchiveVerification, LockInCardRequest, BetaFeedback,
)


def admin(client):
    with client.session_transaction() as state:
        state["ledger_admin_authenticated"] = True
    response = client.get("/admin/development")
    assert response.status_code == 200
    with client.session_transaction() as state:
        return state["vault_admin_workspace_csrf"]


def test_admin_overview_reuses_existing_routes_and_pending_sources(website, database):
    with database[1].begin() as db:
        db.add(VaultGatheringSubmission(
            title="Studio Event", gathering_type="lab", start_date="2026-12-05",
            start_time="18:00", end_time="20:00", hosts="Studio",
            address="123 Example Street", status="pending",
            created_at=datetime(2026, 11, 1, 12)))
        db.add(BetaFeedback(email="feedback@example.org", message="Beta issue",
                            status="new", created_at=datetime(2026, 11, 3, 10)))
        db.add(VaultArchiveVerification(record_slug="example-event", visitor_hash="hash1",
                                         vote="disputed", explanation="Needs verification",
                                         moderation_status="pending",
                                         created_at=datetime(2026, 11, 2, 8)))
    client = website.test_client()
    assert client.get("/admin").status_code in (302, 303, 401, 403)
    token = admin(client)
    html = client.get("/admin").get_data(as_text=True)
    assert "Activity" in html and "LAST 30 DAYS" in html
    assert "Development" in html and "Analytics" in html
    assert html.index("Beta feedback") < html.index("example-event") < html.index("Studio Event")
    assert client.get("/admin/review-queue?section=events").status_code == 303
    assert client.get("/admin/analytics").status_code == 200


def test_pending_links_without_queue(website, database):
    with database[1].begin() as db:
        db.add(BetaFeedback(email="x@example.org", message="Feedback", status="new", created_at=datetime.utcnow()))
    client=website.test_client()
    admin(client)
    html=client.get("/admin").get_data(as_text=True)
    assert "Needs attention" in html
    assert 'aria-label="Beta feedback: 1 pending"' in html
    assert "Review Queue" not in html
    assert client.get("/admin/review-queue").status_code == 303


def test_development_actions_are_protected_and_preserve_existing_records(website, database):
    client = website.test_client()
    assert client.get("/admin/development").status_code in (302, 303, 401, 403)
    token = admin(client)
    url = "/admin/development/create"
    assert client.post(url, data={"title": "Test improvement", "area": "site"}).status_code == 400
    response = client.post(url, data={"csrf_token": token, "title": "Test improvement",
                                      "area": "archive", "description": "Fix layout"})
    assert response.status_code == 303
    with database[1]() as db:
        item = db.query(VaultDevelopmentItem).one()
        assert item.status == "needs_review" and item.area == "archive"
        ident = item.id
    assert client.post(f"/admin/development/{ident}/status",
                       data={"csrf_token": token, "status": "invalid"}).status_code == 400
    changed = client.post(f"/admin/development/{ident}/status",
                          data={"csrf_token": token, "status": "active"})
    assert changed.status_code == 303
    with database[1]() as db:
        assert db.get(VaultDevelopmentItem, ident).status == "active"


def test_public_feedback_is_private_csrf_protected_and_convertible(website, database):
    client = website.test_client()
    get = client.get("/feedback/development")
    assert get.status_code == 200
    with client.session_transaction() as state:
        token = state["vault_development_feedback_csrf"]
    fields = {"title": "Improve navigation", "details": "Please improve the archive menus",
              "area": "archive", "email": "person@example.org", "csrf_token": token}
    assert client.post("/feedback/development", data=dict(fields, csrf_token="wrong")).status_code == 400
    assert client.post("/feedback/development", data=dict(fields, website="bot")).status_code == 400
    posted = client.post("/feedback/development", data=fields)
    assert posted.status_code == 200
    assert "Feedback received" in posted.get_data(as_text=True)
    assert client.post("/feedback/development", data=fields).status_code == 400
    with database[1]() as db:
        item = db.query(VaultDevelopmentFeedback).one()
        assert item.status == "new" and item.contact_email == "person@example.org"
        feedback_id = item.id
    admin_token = admin(client)
    assert "person@example.org" not in client.get("/").get_data(as_text=True)
    converted = client.post(f"/admin/development/feedback/{feedback_id}/decision",
                            data={"csrf_token": admin_token, "decision": "converted"})
    assert converted.status_code == 303
    with database[1]() as db:
        feedback = db.get(VaultDevelopmentFeedback, feedback_id)
        assert feedback.status == "converted"
        entry = db.query(VaultDevelopmentItem).filter_by(source_feedback_id=feedback_id).one()
        assert entry.title == "Improve navigation" and entry.status == "needs_review"
    assert client.post(f"/admin/development/feedback/{feedback_id}/decision",
                       data={"csrf_token": admin_token, "decision": "converted"}).status_code == 400


def test_archive_and_lock_in_review_controls_do_not_publish_records(website, database):
    with database[1].begin() as db:
        db.add(VaultArchiveVerification(record_slug="test-record", visitor_hash="anon",
                                         vote="disputed", moderation_status="pending"))
        db.add(LockInCardRequest(card_type="trick", card_name="Example Trick",
                                 contact_email="priv@example.org", details_json="{}",
                                 status="pending"))
    client = website.test_client()
    token = admin(client)
    response = client.get("/admin/review-records")
    assert response.status_code == 200
    assert "Example Trick" in response.get_data(as_text=True)
    with database[1]() as db:
        archive_id = db.query(VaultArchiveVerification).one().id
        card_id = db.query(LockInCardRequest).one().id
    assert client.post(f"/admin/review-records/lock-in/{card_id}",
                       data={"decision": "approved"}).status_code == 400
    response = client.post(f"/admin/review-records/lock-in/{card_id}",
                           data={"decision": "approved", "csrf_token": token})
    assert response.status_code == 303
    response = client.post(f"/admin/review-records/archive/{archive_id}",
                           data={"decision": "rejected", "csrf_token": token})
    assert response.status_code == 303
    with database[1]() as db:
        assert db.get(LockInCardRequest, card_id).status == "approved"
        assert db.get(VaultArchiveVerification, archive_id).moderation_status == "rejected"


def test_admin_navigation_points_to_sections(website, database):
    client=website.test_client()
    admin(client)
    html=client.get("/admin").get_data(as_text=True)
    assert 'class="ledger-admin-nav"' in html
    assert 'class="lfv-admin-theme-toggle"' in html
    assert "Review Queue" not in html
    assert client.get("/admin/review-records?source=archive").status_code == 200

def test_admin_login_redirects_to_unified_overview(website, monkeypatch):
    import os
    monkeypatch.setenv("ADMIN_USERNAME", "owner-test")
    monkeypatch.setenv("ADMIN_PASSWORD", "password-test")
    client = website.test_client()
    with client.session_transaction() as state:
        state["ledger_admin_authenticated"] = True
    response = client.get("/admin/login")
    assert response.status_code in (302, 303)
    assert response.headers["Location"].endswith("/admin")


def test_admin_overview_date_scope_and_simple_workspaces(website, database):
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    with database[1].begin() as db:
        db.add(VaultDevelopmentItem(title="Current activity", area="site",
                                    updated_at=now-timedelta(days=2)))
        db.add(VaultDevelopmentItem(title="Too old for overview", area="site",
                                    updated_at=now-timedelta(days=40)))
    client=website.test_client()
    admin(client)
    overview=client.get("/admin")
    html=overview.get_data(as_text=True)
    assert 'class="lfv-admin-overview__list"' in html
    assert "Current activity" in html
    assert "Too old for overview" not in html
    assert "Recent Activity" not in html
    assert "Needs attention" in html
    assert "Review Queue" not in html
    assert "Workspace" in html
    assert "lfv-admin-overview__tools" in html
    assert (now-timedelta(days=2)).strftime("%m-%d-%Y") in html
    assert client.get("/admin?page=0").status_code == 400
