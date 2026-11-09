"""Admin review queue, editing, publication and single-occurrence overrides."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from dca_rebuild.models import (
    VaultGatheringSubmission, VaultGatheringReviewHistory, VaultGatheringOccurrenceOverride,
)
from dca_rebuild.upcoming_calendar import upcoming_calendar


def _admin(client):
    with client.session_transaction() as sess:
        sess["ledger_admin_authenticated"] = True
    response = client.get("/admin/gatherings")
    assert response.status_code == 200
    with client.session_transaction() as sess:
        return sess["lfv_gathering_admin_csrf"]


def _event(database, title="Open Lab", **kwargs):
    day = (datetime.now(ZoneInfo("America/New_York")).date() + timedelta(days=8)).isoformat()
    props = dict(
        title=title, gathering_type="lab", start_date=day,
        start_time="18:00", end_time="20:00", hosts="Community Host",
        address="123 Main Street, New York, NY", status="pending",
    )
    props.update(kwargs)
    with database[1].begin() as db:
        item = VaultGatheringSubmission(**props)
        db.add(item)
        db.flush()
        return item.id, item.start_date


def _fields(day, title="Updated Lab", **kwargs):
    data = dict(
        title=title, gathering_type="lab", description="An edited description",
        start_date=day, end_date="", start_time="17:00", end_time="19:00",
        recurrence_rule="none", recurrence_until="", venue="Community Hall",
        city="Harlem", address="456 Main Street, New York, NY",
        hosts="Updated Host", admission="Free", link="https://example.org/event",
        contact_name="Organizer", contact_email="organizer@example.org",
        additional_notes="Private admin note",
    )
    data.update(kwargs)
    return data


def test_admin_queue_filters_search_and_oldest_first(website, database):
    first, day = _event(database, title="First Lab")
    second, _ = _event(database, title="Second Class", gathering_type="class")
    third, _ = _event(database, title="Third Lab", status="rejected")
    client = website.test_client()
    _admin(client)
    queue = client.get("/admin/gatherings").get_data(as_text=True)
    assert queue.index("First Lab") < queue.index("Second Class") < queue.index("Third Lab")
    pending = client.get("/admin/gatherings?status=pending").get_data(as_text=True)
    assert "First Lab" in pending and "Second Class" in pending
    assert "Third Lab" not in pending.split('<tbody>', 1)[1]
    classes = client.get("/admin/gatherings?type=class").get_data(as_text=True)
    assert "Second Class" in classes and "First Lab" not in classes.split('<tbody>', 1)[1]
    result = client.get("/admin/gatherings?q=Second").get_data(as_text=True)
    assert "Second Class" in result and "First Lab" not in result.split('<tbody>', 1)[1]
    assert client.get("/admin/gatherings?page=0").status_code == 400
    assert client.get("/admin/gatherings?status=invalid").status_code == 400


def test_event_edit_is_csrf_protected_and_preserves_private_details(website, database):
    event_id, day = _event(database, contact_email="original@example.org")
    client = website.test_client()
    token = _admin(client)
    url = f"/admin/gatherings/{event_id}"
    assert client.post(url, data=_fields(day)).status_code == 400 or client.post(url, data=_fields(day)).status_code in (302, 303)
    result = client.post(url, data=dict(_fields(day), csrf_token=token))
    assert result.status_code == 303
    with database[1]() as db:
        item = db.get(VaultGatheringSubmission, event_id)
        assert item.title == "Updated Lab"
        assert item.start_time == "17:00"
        assert item.contact_email == "organizer@example.org"
        assert item.additional_notes == "Private admin note"
        audit = db.query(VaultGatheringReviewHistory).filter_by(submission_id=event_id).all()
        assert any(a.action == "edit" for a in audit)
    detail = client.get(f"/calendar/events/{day}/updated-lab")
    assert detail.status_code == 404  # Still pending.
    # Unknown or invalid fields must not rewrite the saved record.
    result = client.post(url, data=dict(_fields(day, title="Bad Title", end_time="12:00"), csrf_token=token))
    assert result.status_code == 303
    with database[1]() as db:
        assert db.get(VaultGatheringSubmission, event_id).title == "Updated Lab"


def test_publish_unpublish_restore_and_review_history(website, database):
    event_id, day = _event(database)
    client = website.test_client()
    token = _admin(client)
    def act(name):
        return client.post(f"/admin/gatherings/{event_id}/{name}", data={"csrf_token": token})
    assert act("approve").status_code == 303
    assert client.get(f"/calendar/events/{day}/open-lab").status_code == 200
    assert act("unpublish").status_code == 303
    assert client.get(f"/calendar/events/{day}/open-lab").status_code == 404
    assert act("restore").status_code == 303
    assert client.get(f"/calendar/events/{day}/open-lab").status_code == 200
    assert act("reject").status_code == 303
    assert client.get(f"/calendar/events/{day}/open-lab").status_code == 404
    assert act("reconsider").status_code == 303
    with database[1]() as db:
        item = db.get(VaultGatheringSubmission, event_id)
        assert item.status == "pending"
        actions = [a.action for a in db.query(VaultGatheringReviewHistory).filter_by(submission_id=event_id).order_by(VaultGatheringReviewHistory.id).all()]
        assert actions == ["approve", "unpublish", "restore", "reject", "reconsider"]
    assert act("unpublish").status_code == 400


def test_single_recurring_occurrence_cancellation_preserves_other_days(website, database):
    monday = date.today() + timedelta(days=(7 - date.today().weekday()) % 7 + 7)
    first_id, _ = _event(database, "Weekly Practice", start_date=monday.isoformat(),
                          recurrence_rule="weekly", recurrence_weekdays="0",
                          status="approved")
    following = monday + timedelta(days=7)
    client = website.test_client()
    token = _admin(client)
    action_url = f"/admin/gatherings/{first_id}/occurrences"
    def titles(on):
        return [x["title"] for x in upcoming_calendar(
            today=on, window_days=1, session_factory=database[1])["events"]]
    assert "Weekly Practice" in titles(monday)
    response = client.post(action_url, data=dict(
        csrf_token=token, action="cancel", date=monday.isoformat(), reason="Studio closed"))
    assert response.status_code == 303
    assert "Weekly Practice" not in titles(monday)
    assert "Weekly Practice" in titles(following)
    with database[1]() as db:
        override = db.query(VaultGatheringOccurrenceOverride).filter_by(submission_id=first_id).one()
        assert override.reason == "Studio closed"
    response = client.post(action_url, data=dict(csrf_token=token, action="restore", date=monday.isoformat()))
    assert response.status_code == 303
    assert "Weekly Practice" in titles(monday)


def test_approved_same_title_date_events_not_removed(website, database):
    first, day = _event(database, title="Neighborhood Lab", status="approved")
    second, _ = _event(database, title="Neighborhood Lab", status="approved")
    client = website.test_client()
    token = _admin(client)
    review = client.get(f"/admin/gatherings/{first}").get_data(as_text=True)
    assert f"#{second}" in review
    events = [e for e in upcoming_calendar(today=date.fromisoformat(day), window_days=1,
                                           session_factory=database[1])["events"]
              if e["title"] == "Neighborhood Lab"]
    assert len(events) == 2
    assert len({e["href"] for e in events}) == 2
    assert all(client.get(e["href"]).status_code == 200 for e in events)


def test_event_review_requires_admin(website, database):
    event_id, _ = _event(database)
    client = website.test_client()
    result = client.get("/admin/gatherings")
    assert result.status_code in (302, 303, 401, 403)
    result = client.get(f"/admin/gatherings/{event_id}")
    assert result.status_code in (302, 303, 401, 403)
