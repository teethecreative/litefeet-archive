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
    assert "Needs Attention" in html
    assert "Development" in html and "Analytics" in html
    assert html.index("Studio Event") < html.index("example-event") < html.index("Beta issue")
    assert client.get("/admin/review-queue?section=events").status_code == 200
    assert client.get("/admin/review-queue?sort=invalid").status_code == 400
    assert client.get("/admin/review-queue?page=0").status_code == 400
    assert client.get("/admin/analytics").status_code == 200


def test_queue_global_sort_filter_and_page_order(website, database):
    with database[1].begin() as db:
        for i in range(14):
            db.add(VaultGatheringSubmission(
                title=f"Event {i:02}", gathering_type="class",
                start_date="2026-12-05", hosts="Host", address="Test address",
                start_time="09:00", end_time="11:00", status="pending",
                created_at=datetime(2026, 11, 1) + timedelta(hours=i)))
        db.add(BetaFeedback(email="x@example.org", message="First beta",
                            status="new", created_at=datetime(2026, 10, 29)))
    client = website.test_client()
    admin(client)
    first = client.get("/admin/review-queue?sort=oldest").get_data(as_text=True)
    second = client.get("/admin/review-queue?sort=oldest&page=2").get_data(as_text=True)
    assert "First beta" in first and "Event 00" in first
    assert "Event 13" in second and "Event 00" not in second
    assert "15 pending items" in first
    newest = client.get("/admin/review-queue?sort=newest").get_data(as_text=True)
    assert newest.index("Event 13") < newest.index("Event 12")
    only_events = client.get("/admin/review-queue?section=events").get_data(as_text=True)
    assert "First beta" not in only_events


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


def test_original_admin_control_room_is_restored_without_losing_new_overview(website, database):
    client = website.test_client()
    assert client.get("/admin/control-room").status_code in (302, 303, 401, 403)
    with client.session_transaction() as state:
        state["ledger_admin_authenticated"] = True
    old = client.get("/admin/control-room")
    assert old.status_code == 200
    html = old.get_data(as_text=True)
    assert "CONTROL" in html and "ROOM" in html
    assert 'id="archive"' in html
    assert 'id="awards"' in html
    assert 'id="community"' in html
    assert "EVENT SUBMISSIONS" in html
    assert 'href="/admin"' in html
    assert 'href="/admin/control-room"' in html
    new = client.get("/admin")
    assert new.status_code == 200
    assert "Needs Attention" in new.get_data(as_text=True)


def test_admin_access_is_in_public_footer_not_main_navigation(website):
    client = website.test_client()
    for path in ("/", "/archive", "/awards"):
        response = client.get(path)
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert 'class="lfv-footer-admin-link" href="/admin">Admin</a>' in html
        assert 'href="/admin"' not in html.split("</nav>", 1)[0]
    # Footer link does not grant administrative access.
    assert client.get("/admin").status_code in (302, 303, 401, 403)
