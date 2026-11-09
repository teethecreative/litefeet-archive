"""Community submission and publishing rules for the public 30-day calendar."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from dca_rebuild.models import VaultGatheringSubmission
from dca_rebuild.upcoming_calendar import upcoming_calendar


def test_submit_form_accepts_battles_classes_labs_and_linkups(website):
    client = website.test_client()
    response = client.get("/submit")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "BATTLE / COMPETITION" in html
    assert "LAB / SESSION" in html
    assert "LINK-UP / MEET-UP" in html
    assert "WORKSHOP" in html
    assert "CLASS" in html
    assert "No flyer or account required." in html
    assert "name=\"csrf_token\"" in html


def test_submission_requires_csrf_and_saves_pending_only(website, database):
    client = website.test_client()
    soon = (datetime.now(ZoneInfo("America/New_York")).date() + timedelta(days=5)).isoformat()
    data = dict(title="Sunday Lab Session", gathering_type="lab",
                start_date=soon, venue="The Studio", city="Harlem",
                contact_email="organizer@example.com",
                additional_notes="Do not publish contact information.",
                link="https://example.com/session")
    assert client.post("/submit", data=data).status_code == 400
    client.get("/submit")
    with client.session_transaction() as sess:
        token = sess["lfv_submit_csrf"]
    response = client.post("/submit", data=dict(data, csrf_token=token))
    assert response.status_code == 303
    assert response.headers["Location"].endswith("/submit/thank-you")
    with database[1]() as db:
        item = db.query(VaultGatheringSubmission).one()
        assert item.title == "Sunday Lab Session"
        assert item.gathering_type == "lab"
        assert item.status == "pending"
        assert item.contact_email == "organizer@example.com"
    calendar = upcoming_calendar(session_factory=database[1])
    assert not any(x["title"] == "Sunday Lab Session" for x in calendar["events"])


def test_admin_approval_publishes_only_public_details(website, database):
    client = website.test_client()
    soon = (datetime.now(ZoneInfo("America/New_York")).date() + timedelta(days=7)).isoformat()
    with database[1].begin() as db:
        entry = VaultGatheringSubmission(title="Community Workshop", gathering_type="workshop",
                    start_date=soon, venue="Workshop Studio",
                    contact_email="private@example.com",
                    additional_notes="Private organizer note", status="pending")
        db.add(entry)
        db.flush()
        pk = entry.id
    with client.session_transaction() as sess:
        sess["ledger_admin_authenticated"] = True
    result = client.get("/admin/gatherings")
    assert result.status_code == 200
    assert "Community Workshop" in result.get_data(as_text=True)
    with client.session_transaction() as sess:
        token = sess["lfv_gathering_admin_csrf"]
    response = client.post(f"/admin/gatherings/{pk}/approve", data={"csrf_token": token})
    assert response.status_code == 303
    calendar = upcoming_calendar(session_factory=database[1])
    entries = [e for e in calendar["events"] if e["title"] == "Community Workshop"]
    assert len(entries) == 1
    assert entries[0]["status"] == "COMMUNITY"
    text = client.get(f"/calendar?date={soon}&day={soon}").get_data(as_text=True)
    assert "Community Workshop" in text
    assert "private@example.com" not in text
    assert "Private organizer note" not in text


def test_submission_validates_future_date_and_url(website, database):
    client = website.test_client()
    client.get("/submit")
    with client.session_transaction() as sess:
        token = sess["lfv_submit_csrf"]
    yesterday = (datetime.now(ZoneInfo("America/New_York")).date() - timedelta(days=1)).isoformat()
    response = client.post("/submit", data=dict(csrf_token=token, title="Past Battle",
                      gathering_type="battle", start_date=yesterday))
    assert response.status_code == 302
    future = (datetime.now(ZoneInfo("America/New_York")).date() + timedelta(days=6)).isoformat()
    response = client.post("/submit", data=dict(csrf_token=token, title="Bad Link",
                      gathering_type="battle", start_date=future, link="javascript:alert(1)"))
    assert response.status_code == 302
    with database[1]() as db:
        assert db.query(VaultGatheringSubmission).count() == 0


def test_weekly_submission_expands_on_selected_weekdays_only(website, database):
    from datetime import date
    from werkzeug.datastructures import MultiDict
    client = website.test_client()
    today = datetime.now(ZoneInfo("America/New_York")).date()
    monday = today + timedelta(days=(7 - today.weekday()) % 7)
    if monday <= today:
        monday += timedelta(days=7)
    client.get("/submit")
    with client.session_transaction() as sess:
        token = sess["lfv_submit_csrf"]
    response = client.post("/submit", data=MultiDict([
        ("csrf_token", token),
        ("title", "Let's Lab at the ARC"),
        ("gathering_type", "lab"),
        ("start_date", monday.isoformat()),
        ("start_time", "18:00"),
        ("end_time", "21:30"),
        ("venue", "The ARC"),
        ("recurrence_rule", "weekly"),
        ("recurrence_weekdays", "0"),
        ("recurrence_weekdays", "1"),
        ("recurrence_weekdays", "2"),
    ]))
    assert response.status_code == 303
    with database[1].begin() as db:
        item = db.query(VaultGatheringSubmission).filter_by(title="Let's Lab at the ARC").one()
        assert item.status == "pending"
        assert item.recurrence_rule == "weekly"
        assert item.recurrence_weekdays == "0,1,2"
        item.status = "approved"
    calendar = upcoming_calendar(today=monday, session_factory=database[1])
    days = [date.fromisoformat(e["date"]).weekday() for e in calendar["events"] if e["title"] == "Let's Lab at the ARC"]
    assert days
    assert set(days) == {0, 1, 2}


def test_repeating_event_rejects_end_date_conflict(website, database):
    client = website.test_client()
    start = (datetime.now(ZoneInfo("America/New_York")).date() + timedelta(days=5)).isoformat()
    client.get("/submit")
    with client.session_transaction() as sess:
        token = sess["lfv_submit_csrf"]
    response = client.post("/submit", data=dict(
        csrf_token=token, title="Bad Repeat", gathering_type="lab",
        start_date=start, end_date=start, recurrence_rule="weekly",
    ))
    assert response.status_code == 302
    with database[1]() as db:
        assert db.query(VaultGatheringSubmission).filter_by(title="Bad Repeat").count() == 0


def test_homepage_preview_is_paginated_and_links_to_calendar(website):
    client = website.test_client()
    home = client.get("/")
    assert home.status_code == 200
    html = home.get_data(as_text=True)
    assert html.count('class="lfv5-calendar-event"') <= 5
    assert 'View Full Calendar' in html
    assert 'Add an Event' in html
    assert 'href="/calendar"' in html
    assert 'calendar_page=2' in html or 'calendar_page=2' in home.headers.get("Location", "") or 'calendar_page=2' in html.replace("&amp;", "&")
    chosen = client.get("/?calendar_day=2026-11-10")
    assert chosen.status_code == 200
    chosen_html = chosen.get_data(as_text=True)
    assert "Showing 2026-11-10 only" in chosen_html
    assert chosen_html.count('class="lfv5-calendar-event"') == 2
    assert 'Show all events' in chosen_html
    page_two = client.get("/?calendar_page=2")
    assert page_two.status_code == 200
    assert page_two.get_data(as_text=True).count('class="lfv5-calendar-event"') <= 5


def test_calendar_day_filters_and_detail_stays_on_site(website):
    client = website.test_client()
    # Known recurring events: Tue has two, Fri has none.
    selected = "2026-11-10"
    day = client.get("/calendar?date=" + selected + "&day=" + selected)
    assert day.status_code == 200
    html = day.get_data(as_text=True)
    assert "Events on November 10, 2026" in html
    assert "Let&#39;s Lab at the ARC" in html or "Let's Lab at the ARC" in html
    assert "Teen Nite" in html
    assert "November 11, 2026" not in html.split('class="lfv-calendar-full-list"', 1)[-1]
    assert 'href="/calendar/events/2026-11-10/let-s-lab-at-the-arc"' in html
    assert 'View all dates this month' in html
    empty = client.get("/calendar?date=2026-11-13&day=2026-11-13")
    assert empty.status_code == 200
    assert "No events are listed for this day" in empty.get_data(as_text=True)
    invalid = client.get("/calendar?date=2026-11-10&day=2026-12-10")
    assert invalid.status_code == 400

    details = client.get("/calendar/events/2026-11-10/teen-nite-litefeet-harlem-shake-lab")
    assert details.status_code == 200
    body = details.get_data(as_text=True)
    assert "Union Settlement" in body
    assert "View source / more information" in body
    assert "https://www.instagram.com/teennightnyc/" in body
    not_found = client.get("/calendar/events/2026-11-10/does-not-exist")
    assert not_found.status_code == 404
