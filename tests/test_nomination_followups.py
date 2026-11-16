"""Returning nomination follow-ups are private and never count as new nominations."""
from datetime import timedelta

from dca_rebuild.models import (
    DCANominationSubmission, DCANominee, NominationCooldown,
)
from dca_rebuild.nomination_service import add_nomination
from dca_rebuild.phase9e import NominationDetail9E, NomineeQualificationReason9E
from conftest import identify

PATH = "/awards/dancers-choice/my-nomination-followups"
STATUS = "/awards/dancers-choice/followup-status"


def old_nomination(database, client, name="Historic Nominee", category=1, reason=None):
    with client.session_transaction() as sess:
        who = sess["lf9e_recent_hash"]
    with database[1].begin() as db:
        nominee, created = add_nomination(
            db, edition_id=database[2], category_id=category,
            name=name, submitter_hash=who, description=reason
        )
        assert created
        submission = db.query(DCANominationSubmission).filter_by(
            nominee_id=nominee.id, submitter_hash=who
        ).one()
        if reason is not None:
            db.add(NominationDetail9E(
                submission_id=submission.id, justification=reason
            ))
        nominee_id = nominee.id
    return nominee_id


def test_anonymous_cannot_see_personal_followups(website):
    client = website.test_client()
    assert client.get(STATUS).get_json() == {"needs_details": 0}
    assert client.get(PATH).status_code == 302
    page = client.get("/").get_data(as_text=True)
    assert 'nomination-followups.js' not in page


def test_returning_nominator_sees_private_reminder_only_for_missing_details(website, database):
    client = website.test_client()
    identify(client)
    target = old_nomination(database, client)
    old_nomination(database, client, name="Complete Nominee", category=2,
                   reason="Active in LiteFeet sessions during 2026.")
    status = client.get(STATUS)
    assert status.get_json() == {"needs_details": 1}
    assert status.headers["Cache-Control"] == "private, no-store"
    homepage = client.get("/").get_data(as_text=True)
    assert 'nomination-followups.js' in homepage
    assert 'nomination-followups.css' in homepage
    assert 'Historic Nominee' not in homepage

    response = client.get(PATH)
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "private, no-store"
    assert response.headers["X-Robots-Tag"] == "noindex, nofollow"
    html = response.get_data(as_text=True)
    assert 'Historic Nominee' in html
    assert 'Complete Nominee' not in html
    assert f'value="{target}"' in html


def test_followup_keeps_nomination_total_and_cooldown_unchanged(website, database):
    client = website.test_client()
    identify(client)
    nominee_id = old_nomination(database, client)
    with database[1]() as db:
        original = db.query(DCANominationSubmission).one()
        original_id, original_time = original.id, original.submitted_at
        claim = db.query(NominationCooldown).one()
        original_cooldown = claim.next_eligible_at
    page = client.get(PATH).get_data(as_text=True)
    assert 'Complete your nominations' in page
    with client.session_transaction() as sess:
        csrf = sess["lf9e_followup_csrf"]
    response = client.post(PATH, data={
        "csrf_token": csrf, "nominee_id": nominee_id,
        "reason": "They performed at LiteFeet community sessions in 2026.",
        "evidence_url": "https://example.com/reference",
    })
    assert response.status_code == 303
    assert client.get(STATUS).get_json()["needs_details"] == 0
    with database[1]() as db:
        submissions = db.query(DCANominationSubmission).all()
        assert len(submissions) == 1
        assert submissions[0].id == original_id
        assert submissions[0].submitted_at == original_time
        assert db.query(NominationCooldown).one().next_eligible_at == original_cooldown
        row = db.query(NomineeQualificationReason9E).one()
        assert row.nominee_id == nominee_id
        assert row.moderation_status == "pending"
        assert "community sessions" in row.reason
    assert "You're all caught up" in client.get(PATH).get_data(as_text=True)


def test_user_cannot_complete_another_nominators_record(website, database):
    first = website.test_client()
    identify(first, "one@example.com")
    nominee_id = old_nomination(database, first)
    second = website.test_client()
    identify(second, "two@example.com")
    second.get(PATH)
    with second.session_transaction() as sess:
        csrf = sess["lf9e_followup_csrf"]
    reply = second.post(PATH, data={
        "csrf_token": csrf, "nominee_id": nominee_id,
        "reason": "I want to recognize their recent community contributions.",
    })
    assert reply.status_code == 404
    with database[1]() as db:
        assert db.query(NomineeQualificationReason9E).count() == 0


def test_repeat_submission_and_invalid_csrf_are_blocked(website, database):
    client = website.test_client()
    identify(client)
    nominee_id = old_nomination(database, client)
    client.get(PATH)
    with client.session_transaction() as sess:
        csrf = sess["lf9e_followup_csrf"]
    assert client.post(PATH, data={
        "csrf_token": "bad", "nominee_id": nominee_id,
        "reason": "They contributed at community events throughout 2026.",
    }).status_code == 400
    payload = {
        "csrf_token": csrf, "nominee_id": nominee_id,
        "reason": "They contributed at community events throughout 2026.",
    }
    assert client.post(PATH, data=payload).status_code == 303
    assert client.post(PATH, data=payload).status_code == 404
    with database[1]() as db:
        assert db.query(NomineeQualificationReason9E).count() == 1


def test_existing_supplement_is_not_requested_again(website, database):
    client = website.test_client()
    identify(client)
    nominee_id = old_nomination(database, client)
    with client.session_transaction() as sess:
        who = sess["lf9e_recent_hash"]
    with database[1].begin() as db:
        db.add(NomineeQualificationReason9E(
            edition_id=database[2], nominee_id=nominee_id,
            submitter_hash=who, reason="Supporting documentation submitted.",
            moderation_status="pending",
        ))
    assert client.get(STATUS).get_json()["needs_details"] == 0


def test_successful_nomination_keeps_reminder_on_signed_session(website):
    client = website.test_client()
    csrf = identify(client)
    response = client.post("/awards/dancers-choice/nominations", data={
        "csrf_token": csrf, "category_id": 1, "name": "Verified Submission",
        "reason": "Their work at LiteFeet events was documented in 2026.",
    })
    assert response.status_code == 302
    with client.session_transaction() as sess:
        assert sess.get("lf9e_reminder_hash") == sess.get("lf9e_recent_hash")
    result = client.post("/awards/dancers-choice/nominations", data={
        "csrf_token": csrf, "action": "done", "next": "standings",
    })
    assert result.status_code == 303
    with client.session_transaction() as sess:
        assert "lf9e_recent_hash" not in sess
        assert sess.get("lf9e_reminder_hash")
