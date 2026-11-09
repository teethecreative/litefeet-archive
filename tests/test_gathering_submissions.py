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
                start_date=soon, start_time="18:00", end_time="20:00",
                hosts="Community Organizer", address="123 Main Street, New York, NY",
                venue="The Studio", city="Harlem",
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
                      gathering_type="battle", start_date=yesterday, start_time="18:00", end_time="20:00",
                      hosts="Organizer", address="123 Main Street"))
    assert response.status_code == 302
    future = (datetime.now(ZoneInfo("America/New_York")).date() + timedelta(days=6)).isoformat()
    response = client.post("/submit", data=dict(csrf_token=token, title="Bad Link",
                      gathering_type="battle", start_date=future, start_time="18:00", end_time="20:00",
                      hosts="Organizer", address="123 Main Street", link="javascript:alert(1)"))
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
        ("hosts", "ARC Team"),
        ("address", "123 Main Street, New York, NY"),
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
    assert 'href="/events/let-s-lab-at-the-arc/2026-11-10"' in html
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


def test_submission_requires_time_host_and_location(website, database):
    client = website.test_client()
    day = (datetime.now(ZoneInfo("America/New_York")).date() + timedelta(days=3)).isoformat()
    client.get("/submit")
    with client.session_transaction() as sess:
        token = sess["lfv_submit_csrf"]
    common = dict(csrf_token=token, title="Community Class",
                  gathering_type="class", start_date=day)
    incomplete = [
        dict(start_time="18:00", end_time="19:00", hosts="Teacher"),
        dict(start_time="18:00", end_time="19:00", address="123 Main St"),
        dict(start_time="18:00", hosts="Teacher", address="123 Main St"),
        dict(start_time="19:00", end_time="18:00", hosts="Teacher", address="123 Main St"),
    ]
    for fields in incomplete:
        response = client.post("/submit", data=dict(common, **fields))
        assert response.status_code == 302
    with database[1]() as db:
        assert db.query(VaultGatheringSubmission).count() == 0


def test_yearly_virtual_submission_is_pending(website, database):
    client = website.test_client()
    day = (datetime.now(ZoneInfo("America/New_York")).date() + timedelta(days=7)).isoformat()
    client.get("/submit")
    with client.session_transaction() as sess:
        token = sess["lfv_submit_csrf"]
    response = client.post("/submit", data=dict(
        csrf_token=token, title="Online Annual Event", gathering_type="event",
        start_date=day, start_time="12:00", end_time="13:00",
        hosts="Online Organizer", virtual="1", address="Zoom link sent upon registration",
        recurrence_rule="yearly",
    ))
    assert response.status_code == 303
    with database[1]() as db:
        item = db.query(VaultGatheringSubmission).one()
        assert item.recurrence_rule == "yearly"
        assert item.virtual is True
        assert item.address == "Zoom link sent upon registration"
        assert item.status == "pending"


def test_calendar_grid_shows_event_titles_and_day_navigation(website):
    client = website.test_client()
    response = client.get("/calendar?date=2026-11-10")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    grid = html.split('class="lfv-calendar-month-grid"', 1)[1].split("</table>", 1)[0]
    assert "lfv-calendar-category-counts" not in grid
    assert "lfv-calendar-tile-event" in grid
    assert "Let&#39;s Lab at the ARC" in grid or "Let's Lab at the ARC" in grid
    assert "Teen Nite" in grid
    assert '/events/let-s-lab-at-the-arc/2026-11-10' in grid
    assert "day=2026-11-10" in grid.replace("&amp;", "&")
    assert "lfv-calendar-event-copy" in html


def test_calendar_busy_day_shows_two_events_and_see_more(website, database):
    client = website.test_client()
    with database[1].begin() as db:
        db.add(VaultGatheringSubmission(
            title="Community Dance Class", gathering_type="class",
            start_date="2026-11-10", status="approved",
            start_time="17:00", end_time="18:00",
            hosts="Dance Instructor", address="123 Main Street"))
    html = client.get("/calendar?date=2026-11-10").get_data(as_text=True)
    grid = html.split('class="lfv-calendar-month-grid"', 1)[1].split("</table>", 1)[0]
    assert "See 1 more" in grid
    assert "day=2026-11-10" in grid.replace("&amp;", "&")
    assert grid.count('class="lfv-calendar-tile-event"') >= 2
    assert "Community Dance Class" in html
    assert '/events/community-dance-class/2026-11-10' in html
    day = client.get("/calendar?date=2026-11-10&day=2026-11-10").get_data(as_text=True)
    assert "Community Dance Class" in day
    assert "Teen Nite" in day
    assert "Let&#39;s Lab" in day or "Let's Lab" in day


def test_upcoming_calendar_category_counts_are_per_day(website, database):
    from datetime import date
    calendar = upcoming_calendar(today=date(2026, 11, 10),
                                 session_factory=database[1], window_days=1)
    assert calendar["days"][0]["category_counts"] == [
        {"count": 2, "label": "Lab Sessions"}
    ]


def test_calendar_detail_displays_recurring_schedule_without_duplicate_location(website):
    client = website.test_client()
    response = client.get("/calendar/events/2026-11-11/let-s-lab-at-the-arc")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Lab Session" in html
    assert "Every Monday, Tuesday and Wednesday" in html
    assert "501 Carlton Avenue" in html
    assert "Google Calendar" in html
    assert "Apple / Outlook calendar" in html
    assert "Directions" in html
    # The source venue is not also displayed as the event's descriptive body.
    assert "About this event" not in html
    ics = client.get("/calendar/events/2026-11-11/let-s-lab-at-the-arc/calendar.ics")
    assert ics.status_code == 200
    assert "text/calendar" in ics.content_type
    assert "DTSTART;TZID=America/New_York:20261111T180000" in ics.get_data(as_text=True)


def test_virtual_event_access_and_private_fields_not_exposed(website, database):
    from datetime import date
    chosen = date.today() + timedelta(days=8)
    with database[1].begin() as db:
        db.add(VaultGatheringSubmission(
            title="Virtual Practice Session", gathering_type="lab",
            start_date=chosen.isoformat(), start_time="17:00", end_time="18:00",
            hosts="Online Team", virtual=True,
            address="Zoom joining information provided after registration",
            contact_email="private@example.org",
            additional_notes="Internal moderation note",
            status="approved",
        ))
    client = website.test_client()
    path = f"/calendar/events/{chosen.isoformat()}/virtual-practice-session"
    response = client.get(path)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Virtual event" in html
    assert "How to join" in html
    assert "Zoom joining information provided after registration" in html
    assert "Directions" not in html
    assert "private@example.org" not in html
    assert "Internal moderation note" not in html


def test_multi_day_event_appears_each_day_and_shows_full_range(website, database):
    from datetime import date
    start = datetime.now(ZoneInfo("America/New_York")).date() + timedelta(days=9)
    finish = start + timedelta(days=2)
    with database[1].begin() as db:
        db.add(VaultGatheringSubmission(
            title="Three Day Community Workshop", gathering_type="workshop",
            start_date=start.isoformat(), end_date=finish.isoformat(),
            start_time="13:00", end_time="15:00",
            hosts="Community Organizer", address="123 Main Street, Brooklyn, NY",
            status="approved",
        ))
    calendar = upcoming_calendar(today=start, window_days=3, session_factory=database[1])
    occurrences = [x for x in calendar["events"] if x["title"] == "Three Day Community Workshop"]
    assert [x["date"] for x in occurrences] == [
        start.isoformat(), (start + timedelta(days=1)).isoformat(), finish.isoformat()
    ]
    page = website.test_client().get(
        f"/calendar/events/{(start + timedelta(days=1)).isoformat()}/three-day-community-workshop")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert "Workshop" in html
    assert start.strftime("%B") in html
    assert finish.strftime("%Y") in html
