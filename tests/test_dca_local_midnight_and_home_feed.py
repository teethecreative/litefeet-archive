"""Sitewide local-midnight automatic logout and live homepage nomination feed."""
from datetime import datetime, timezone

from conftest import identify
from dca_rebuild.models import DCANominee, DCANominationSubmission


def test_browser_timezone_is_saved_with_nomination_session(website):
    client = website.test_client()
    client.get("/awards/dancers-choice/nominations")
    with client.session_transaction() as sess:
        csrf = sess["lf9e_nomination_csrf"]
    response = client.post("/awards/dancers-choice/nominations", data={
        "action": "identify",
        "email": "local-day@example.com",
        "csrf_token": csrf,
        "timezone": "America/Los_Angeles",
    })
    assert response.status_code == 302
    with client.session_transaction() as sess:
        assert sess["lf9e_local_timezone"] == "America/Los_Angeles"
        assert len(sess["lf9e_local_verification_day"]) == 10
        assert sess.get("lf9e_recent_hash")


def test_sitewide_logout_after_local_midnight_without_erasing_submissions(website, database, monkeypatch):
    from dca_rebuild import email_verification as v
    client = website.test_client()
    token = identify(client)
    with client.session_transaction() as sess:
        sess["lf9e_local_timezone"] = "America/Los_Angeles"
        sess["lf9e_local_verification_day"] = "2026-11-23"
    # Freeze the server's derived local calendar day at November 23.
    monkeypatch.setattr(v, "_local_day", lambda name, **kwargs: "2026-11-23")
    assert client.get("/awards/dancers-choice/nominations").status_code == 200
    assert "Choose a Category" in client.get("/awards/dancers-choice/nominations").get_data(as_text=True)
    submission = client.post("/awards/dancers-choice/nominations", data={
        "csrf_token": token, "category_id": "1",
        "name": "Local Midnight Dancer",
        "reason": "Participated in LiteFeet battles during the eligibility period.",
    })
    assert submission.status_code in (302, 303)
    # When November 24 begins locally, all DCA participant identity is cleared,
    # but nomination history and per-email cooldowns persist in the DB.
    monkeypatch.setattr(v, "_local_day", lambda name, **kwargs: "2026-11-24")
    html = client.get("/awards/dancers-choice/nominations").get_data(as_text=True)
    assert "VERIFY &amp; CONTINUE" in html
    assert "Choose a Category" not in html
    with client.session_transaction() as sess:
        assert not sess.get("lf9e_recent_hash")
        assert not sess.get("lf9e_verified_hash")
    with database[1]() as db:
        assert db.query(DCANominationSubmission).count() == 1


def test_admin_login_session_is_logged_out_at_local_midnight(website, monkeypatch):
    from dca_rebuild import email_verification as verification
    client = website.test_client()
    with client.session_transaction() as sess:
        sess["ledger_admin_authenticated"] = True
        sess["lf9e_local_timezone"] = "America/New_York"
        sess["lf9e_local_verification_day"] = "2026-11-23"
        sess["dca_moderation_csrf"] = "private-admin-csrf"
    monkeypatch.setattr(verification, "_local_day", lambda name, **kwargs: "2026-11-23")
    assert client.get("/admin").status_code == 200
    monkeypatch.setattr(verification, "_local_day", lambda name, **kwargs: "2026-11-24")
    protected = client.get("/admin")
    assert protected.status_code in (302, 303, 401, 403)
    with client.session_transaction() as sess:
        assert "ledger_admin_authenticated" not in sess
        assert "dca_moderation_csrf" not in sess
        assert "lf9e_local_verification_day" not in sess


def test_local_date_uses_timezone_not_utc():
    from dca_rebuild.email_verification import _local_day
    instant = datetime(2026, 11, 24, 3, 30, tzinfo=timezone.utc)
    assert _local_day("UTC", now=instant) == "2026-11-24"
    assert _local_day("America/New_York", now=instant) == "2026-11-23"
    assert _local_day("America/Los_Angeles", now=instant) == "2026-11-23"


def test_homepage_latest_six_include_real_write_in_submissions(website, database):
    from dca_rebuild import app as app_module
    _, factory, edition_id = database
    with factory.begin() as db:
        top = DCANominee(
            edition_id=edition_id, category_id=1,
            name="Top Performer", normalized_name="top performer",
            moderation_status="approved",
        )
        write_in = DCANominee(
            edition_id=edition_id, category_id=26,
            name="Write In Performer", normalized_name="write in performer",
            moderation_status="pending",
        )
        db.add_all([top, write_in])
        db.flush()
        db.add_all([
            DCANominationSubmission(edition_id=edition_id, nominee_id=top.id,
                                    submitter_hash="top-supporter",
                                    submitted_at=datetime(2026, 11, 23, 12)),
            DCANominationSubmission(edition_id=edition_id, nominee_id=write_in.id,
                                    submitter_hash="write-in-supporter",
                                    submitted_at=datetime(2026, 11, 23, 13)),
        ])
    rows = app_module.latest_dca_nominations(limit=6)
    assert [(row["category"], row["nominee"]) for row in rows] == [
        ("Category 26", "Write In Performer"),
        ("Category 1", "Top Performer"),
    ]
    html = website.test_client().get("/").get_data(as_text=True)
    assert "Latest Nominations" in html
    assert "Write In Performer" in html
    assert "Top Performer" in html
    assert "write-in-supporter" not in html
    assert "top-supporter" not in html
