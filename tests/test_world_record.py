"""LiteFeet World Record interest route and private admin roster."""
from dca_rebuild.models import WorldRecordInterest


def test_world_record_public_page_and_home_link(website):
    client = website.test_client()
    page = client.get("/world-record")
    assert page.status_code == 200
    assert b"Rehearsal Captains" in page.data
    assert b"Rehearsal Spaces" in page.data
    assert b"proposed" in page.data.lower()
    homepage = client.get("/")
    assert b"/world-record" in homepage.data


def _token(client):
    client.get("/world-record")
    with client.session_transaction() as sess:
        return sess["vault_world_record_csrf"]


def test_interest_submission_and_private_admin(website, database):
    client = website.test_client()
    token = _token(client)
    reply = client.post("/world-record", data={
        "csrf_token": token,
        "role": "captain",
        "contact_name": "Test Adult",
        "email": "coach@example.com",
        "dance_name": "Coach Example",
        "team": "Example Team",
        "borough": "Harlem",
        "experience": "Teaching choreography",
        "availability": "Weekends",
        "adult_or_guardian": "yes",
        "contact_permission": "yes",
    }, follow_redirects=True)
    assert reply.status_code == 200
    assert b"Thanks for being part of the plan" in reply.data
    with database[1]() as db:
        rows = db.query(WorldRecordInterest).all()
        assert len(rows) == 1
        assert rows[0].role == "captain"
        assert rows[0].status == "interested"
    # Public pages must never display private participant contact records.
    assert b"coach@example.com" not in client.get("/world-record").data
    assert client.get("/admin/world-record").status_code in (301, 302)
    with client.session_transaction() as sess:
        sess["ledger_admin_authenticated"] = True
    admin = client.get("/admin/world-record")
    assert admin.status_code == 200
    assert b"coach@example.com" in admin.data


def test_world_record_csrf_and_guardian_consent(website, database):
    client = website.test_client()
    client.get("/world-record")
    invalid = client.post("/world-record", data={
        "csrf_token": "wrong", "role": "dancer", "contact_name": "Test Adult",
        "email": "a@example.com", "adult_or_guardian": "yes",
        "contact_permission": "yes",
    })
    assert invalid.status_code == 400
    token = _token(client)
    missing = client.post("/world-record", data={
        "csrf_token": token, "role": "dancer", "contact_name": "Test Adult",
        "email": "a@example.com", "contact_permission": "yes",
    })
    assert missing.status_code == 400
    with database[1]() as db:
        assert db.query(WorldRecordInterest).count() == 0
