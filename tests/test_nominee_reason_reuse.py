"""Existing nominee explanations are shared qualification records, not per-supporter requirements."""
from datetime import datetime

from conftest import identify
from dca_rebuild.models import DCANominee, DCANominationSubmission, DCAEdition
from dca_rebuild.phase9e import (
    NominationDetail9E, NomineeQualificationReason9E,
)
from dca_rebuild.nomination_followups import _followups

PATH = "/awards/dancers-choice/nominations"


def post_nomination(client, email, name, reason=None):
    csrf = identify(client, email)
    data = {"csrf_token": csrf, "category_id": 1, "name": name}
    if reason is not None:
        data["reason"] = reason
    return client.post(PATH, data=data)


def test_supporter_can_nominate_existing_person_without_second_reason(website, database):
    first = website.test_client()
    assert post_nomination(first, "first@example.com", "Existing Nominee",
                           "Attended many LiteFeet battles during the eligibility period.").status_code in (302, 303)
    supporter = website.test_client()
    csrf = identify(supporter, "second@example.com")
    url = "/awards/dancers-choice/nominee-name-check?category_id=1&name=Existing%20Nominee"
    status = supporter.get(url)
    assert status.status_code == 200
    assert status.get_json()["already_listed"] is True
    assert status.get_json()["reason_required"] is False
    with database[1]() as db:
        nominee = db.query(DCANominee).one()
        id_ = nominee.id
        before = db.query(DCANominationSubmission).count()
    form = supporter.get(PATH + f"?category=1&suggestion={id_}&nominate=1").get_data(as_text=True)
    assert "(optional — reason already on file)" in form
    assert 'name="reason" minlength="20" maxlength="2000" rows="4" required' not in form
    submit = supporter.post(PATH, data={
        "csrf_token": csrf, "category_id": 1, "name": "Existing Nominee",
    })
    assert submit.status_code in (302, 303)
    with database[1]() as db:
        assert db.query(DCANominee).count() == 1
        assert db.query(DCANominationSubmission).count() == before + 1
        assert db.query(NominationDetail9E).order_by(NominationDetail9E.id.desc()).first().justification is None


def test_unexplained_existing_nominee_still_requires_reason(website, database):
    with database[1].begin() as db:
        db.add(DCANominee(edition_id=database[2], category_id=1,
                         name="Missing Reason", normalized_name="missing reason",
                         moderation_status="approved"))
    supporter = website.test_client()
    csrf = identify(supporter, "supporter@example.com")
    hint = supporter.get("/awards/dancers-choice/nominee-name-check?category_id=1&name=Missing%20Reason")
    assert hint.get_json()["reason_required"] is True
    response = supporter.post(PATH, data={
        "csrf_token": csrf, "category_id": 1, "name": "Missing Reason",
    })
    assert response.status_code == 400
    with database[1]() as db:
        assert db.query(DCANominationSubmission).count() == 0


def test_pending_supplemental_reason_is_on_file_without_implying_approval(website, database):
    with database[1].begin() as db:
        nominee = DCANominee(edition_id=database[2], category_id=1,
                            name="Existing Reason", normalized_name="existing reason",
                            moderation_status="pending")
        db.add(nominee)
        db.flush()
        db.add(NomineeQualificationReason9E(
            edition_id=database[2], nominee_id=nominee.id,
            submitter_hash="older-supporter",
            reason="Provided video footage of LiteFeet events in this qualifying year.",
            moderation_status="pending",
        ))
    supporter = website.test_client()
    csrf = identify(supporter, "supporter@example.com")
    status = supporter.get("/awards/dancers-choice/nominee-name-check?category_id=1&name=Existing%20Reason")
    assert status.get_json()["reason_required"] is False
    result = supporter.post(PATH, data={
        "csrf_token": csrf, "category_id": 1, "name": "Existing Reason"
    })
    assert result.status_code in (302, 303)
    with database[1]() as db:
        assert db.query(DCANominee).one().moderation_status == "pending"
        assert db.query(NomineeQualificationReason9E).one().moderation_status == "pending"
        assert db.query(DCANominationSubmission).count() == 1


def test_returning_supporter_not_prompted_if_nominee_has_other_reason(database):
    with database[1].begin() as db:
        nominee = DCANominee(
            edition_id=database[2], category_id=1,
            name="Old Nominee", normalized_name="old nominee",
            moderation_status="approved",
        )
        db.add(nominee)
        db.flush()
        db.add(DCANominationSubmission(
            edition_id=database[2], nominee_id=nominee.id,
            submitter_hash="original-supporter", submitted_at=datetime(2026, 11, 1),
        ))
        db.add(NomineeQualificationReason9E(
            edition_id=database[2], nominee_id=nominee.id,
            submitter_hash="other-supporter",
            reason="Recorded battles demonstrate their qualifying LiteFeet contributions.",
            moderation_status="pending",
        ))
    with database[1]() as db:
        assert _followups(db, database[2], "original-supporter") == []
