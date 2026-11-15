"""One-time Resend codes authorize 2026 nomination history (no actual email sent)."""
from datetime import datetime, timedelta

import pytest
from dca_rebuild.email_verification import EmailVerificationCode
from dca_rebuild.models import DCANominationSubmission
from dca_rebuild.nomination_service import add_nomination

PATH = "/awards/dancers-choice/nominations"
VERIFY = "/awards/dancers-choice/verify-email"
FOLLOW = "/awards/dancers-choice/my-nomination-followups"


def enable_verification(monkeypatch):
    monkeypatch.setenv("DCA_2026_VERIFIED_EMAIL_ENABLED", "true")
    monkeypatch.setenv("DCA_2026_FOLLOWUPS_ENABLED", "true")


def sent_codes(monkeypatch):
    received = []
    monkeypatch.setattr(
        "dca_rebuild.email_verification._send_email",
        lambda email, code: received.append((email, code))
    )
    return received


def submit_email(client, email="person@example.com"):
    client.get(PATH)
    with client.session_transaction() as sess:
        token = sess["lf9e_nomination_csrf"]
    result = client.post(PATH, data={
        "csrf_token": token,
        "action": "identify",
        "email": email,
    })
    return result


def verify_email(client, code):
    client.get(VERIFY)
    with client.session_transaction() as sess:
        token = sess["lfv_verify_csrf"]
    return client.post(VERIFY, data={
        "csrf_token": token, "action": "verify", "code": code,
    })


def test_entering_email_sends_code_without_granting_access(website, database, monkeypatch):
    enable_verification(monkeypatch)
    sent = sent_codes(monkeypatch)
    client = website.test_client()
    response = submit_email(client)
    assert response.status_code == 303
    assert response.headers["Location"].endswith(VERIFY)
    assert len(sent) == 1 and sent[0][0] == "person@example.com"
    assert len(sent[0][1]) == 6 and sent[0][1].isdigit()
    assert client.get("/awards/dancers-choice/followup-status").get_json()["needs_details"] == 0
    assert client.get(FOLLOW).status_code == 302
    with client.session_transaction() as sess:
        assert "lf9e_recent_hash" not in sess
        assert "lf9e_verified_hash" not in sess
        assert "person@example.com" not in str(dict(sess))
    with database[1]() as db:
        challenge = db.query(EmailVerificationCode).one()
        assert sent[0][1] not in challenge.code_hash
        assert challenge.attempts == 0
        assert db.query(DCANominationSubmission).count() == 0


def test_verification_unlocks_existing_history_without_new_submission(website, database, monkeypatch):
    enable_verification(monkeypatch)
    sent = sent_codes(monkeypatch)
    first = website.test_client()
    assert submit_email(first).status_code == 303
    assert verify_email(first, sent[-1][1]).status_code == 303
    with first.session_transaction() as sess:
        who = sess["lf9e_verified_hash"]
        assert who == sess["lf9e_recent_hash"]
    with database[1].begin() as db:
        nominee, created = add_nomination(
            db, edition_id=database[2], category_id=1,
            name="Historic Nominee", submitter_hash=who,
        )
        assert created
    second = website.test_client()
    assert submit_email(second).status_code == 429  # Same address resend cooldown.
    with database[1].begin() as db:
        db.query(EmailVerificationCode).update({
            "requested_at": datetime.utcnow() - timedelta(minutes=2)
        })
    assert submit_email(second).status_code == 303
    assert second.get(FOLLOW).status_code == 302
    assert verify_email(second, sent[-1][1]).status_code == 303
    details = second.get(FOLLOW).get_data(as_text=True)
    assert "Historic Nominee" in details
    assert second.get("/awards/dancers-choice/followup-status").get_json() == {"needs_details": 1}
    with database[1]() as db:
        assert db.query(DCANominationSubmission).count() == 1


def test_wrong_code_attempts_expiration_and_replay(website, database, monkeypatch):
    enable_verification(monkeypatch)
    sent = sent_codes(monkeypatch)
    client = website.test_client()
    assert submit_email(client).status_code == 303
    assert verify_email(client, "not-a-code").status_code == 303
    assert verify_email(client, "111111" if sent[-1][1] != "111111" else "222222").status_code == 303
    with database[1]() as db:
        row = db.query(EmailVerificationCode).one()
        assert row.attempts == 1
    for _ in range(4):
        assert verify_email(client, "111111" if sent[-1][1] != "111111" else "222222").status_code == 303
    assert verify_email(client, sent[-1][1]).status_code == 303
    assert client.get(FOLLOW).status_code == 302
    with database[1]() as db:
        assert db.query(EmailVerificationCode).one().attempts == 5
        assert db.query(EmailVerificationCode).one().used_at is not None


def test_expired_code_cannot_be_reused(website, database, monkeypatch):
    enable_verification(monkeypatch)
    sent = sent_codes(monkeypatch)
    client = website.test_client()
    submit_email(client)
    with database[1].begin() as db:
        db.query(EmailVerificationCode).update({
            "expires_at": datetime.utcnow() - timedelta(seconds=1)
        })
    assert verify_email(client, sent[-1][1]).status_code == 303
    with client.session_transaction() as sess:
        assert "lf9e_verified_hash" not in sess


def test_code_is_one_time_and_email_access_is_revocable(website, monkeypatch):
    enable_verification(monkeypatch)
    sent = sent_codes(monkeypatch)
    client = website.test_client()
    submit_email(client)
    code = sent[-1][1]
    assert verify_email(client, code).status_code == 303
    client.get(VERIFY)
    with client.session_transaction() as sess:
        sess.pop("lf9e_verified_hash", None)
        sess.pop("lf9e_verified_at", None)
    assert verify_email(client, code).status_code == 303
    assert client.get(FOLLOW).status_code == 302


def test_account_switch_revokes_previous_verified_address(website, monkeypatch):
    enable_verification(monkeypatch)
    sent = sent_codes(monkeypatch)
    client = website.test_client()
    submit_email(client, "first@example.com")
    verify_email(client, sent[-1][1])
    with client.session_transaction() as sess:
        first_hash = sess["lf9e_verified_hash"]
    client.get(PATH)
    with client.session_transaction() as sess:
        token = sess["lf9e_nomination_csrf"]
    resp = client.post(PATH, data={
        "csrf_token": token, "action": "change-email",
    })
    assert resp.status_code == 303
    with client.session_transaction() as sess:
        assert not sess.get("lf9e_verified_hash")
        assert not sess.get("lf9e_recent_hash")
    submit_email(client, "second@example.com")
    verify_email(client, sent[-1][1])
    with client.session_transaction() as sess:
        assert sess["lf9e_verified_hash"] != first_hash
