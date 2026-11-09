"""Public event calendar, distinct from the historical archive timeline."""
from calendar import monthrange
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urlencode

from flask import abort, render_template, request, Response, url_for

from dca_rebuild.upcoming_calendar import upcoming_calendar, event_slug


def _selected_month(value, today):
    if not value:
        return today.replace(day=1)
    try:
        parsed = date.fromisoformat(value)
    except (ValueError, TypeError):
        abort(400, "Invalid calendar date")
    return parsed.replace(day=1)


def _shift_month(first, step):
    month_index = first.year * 12 + first.month - 1 + step
    year, month_zero = divmod(month_index, 12)
    if not 1 <= year <= 9999:
        return None
    return date(year, month_zero + 1, 1)



def _get_event_for_day(event_date, slug, session_factory):
    try:
        selected_day = date.fromisoformat(event_date)
    except (ValueError, TypeError):
        abort(404)
    calendar = upcoming_calendar(today=selected_day, window_days=1,
                                 session_factory=session_factory)
    event = next((item for item in calendar["events"]
                  if event_slug(item["title"]) == slug), None)
    if event is None:
        abort(404)
    return event


def _calendar_actions(event):
    """Construct per-occurrence calendar actions without relying on browser plugins."""
    location = (event.get("address") or event.get("venue") or "")
    if event.get("virtual"):
        location = event.get("address") or "Online event"
    first_day = event.get("series_start") if event.get("date_range") else event["date"]
    last_day = event.get("series_end") if event.get("date_range") else event["date"]
    date_text = first_day.replace("-", "")
    end_date_text = last_day.replace("-", "")
    start, end = event.get("start_time"), event.get("end_time")
    if start and end:
        start_value = date_text + "T" + start.replace(":", "") + "00"
        end_value = end_date_text + "T" + end.replace(":", "") + "00"
        dates = start_value + "/" + end_value
        timezone = event.get("timezone") or "America/New_York"
    else:
        # Legacy events with unstructured times remain all-day rather than inventing hours.
        following = (date.fromisoformat(last_day) + timedelta(days=1)).strftime("%Y%m%d")
        dates = date_text + "/" + following
        timezone = ""
    params = {
        "action": "TEMPLATE", "text": event["title"], "dates": dates,
        "details": event.get("description") or event.get("notice") or "",
        "location": location,
    }
    if timezone:
        params["ctz"] = timezone
    return {
        "google": "https://calendar.google.com/calendar/render?" + urlencode(params),
        "directions": ("https://www.google.com/maps/search/?" +
                       urlencode({"api": "1", "query": event.get("address")}))
                      if event.get("address") and not event.get("virtual") else "",
    }


def _escape_ics(value):
    return str(value or "").replace("\\", "\\\\").replace("\n", "\\n").replace(",", "\\,").replace(";", "\\;")


def _event_ics(event):
    # Google and downloadable ICS must use the same occurrence and local timezone.
    first_day = event.get("series_start") if event.get("date_range") else event["date"]
    last_day = event.get("series_end") if event.get("date_range") else event["date"]
    day = first_day.replace("-", "")
    last_day_text = last_day.replace("-", "")
    start, end = event.get("start_time"), event.get("end_time")
    timed = bool(start and end)
    if timed:
        zone = event.get("timezone") or "America/New_York"
        begin = "DTSTART;TZID=" + zone + ":" + day + "T" + start.replace(":", "") + "00"
        finish = "DTEND;TZID=" + zone + ":" + last_day_text + "T" + end.replace(":", "") + "00"
    else:
        begin = "DTSTART;VALUE=DATE:" + day
        finish = "DTEND;VALUE=DATE:" + (date.fromisoformat(last_day) + timedelta(days=1)).strftime("%Y%m%d")
    location = event.get("address") or event.get("venue") or ""
    description = event.get("description") or event.get("notice") or ""
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//The LiteFeet Vault//Calendar//EN",
             "BEGIN:VEVENT", "UID:" + _escape_ics(event_slug(event["title"]) + "-" + event["date"] + "@thelitefeetvault.com"),
             "DTSTAMP:" + datetime.utcnow().strftime("%Y%m%dT%H%M%SZ"),
             begin, finish, "SUMMARY:" + _escape_ics(event["title"]),
             "DESCRIPTION:" + _escape_ics(description),
             "LOCATION:" + _escape_ics(location),
             "URL:" + _escape_ics("https://thelitefeetvault.com" + event["href"]),
             "END:VEVENT", "END:VCALENDAR", ""]
    return "\r\n".join(lines)


def install_calendar_pages(app, ns):
    def full_calendar():
        now = datetime.now(ZoneInfo("America/New_York")).date()
        selected = _selected_month(request.args.get("date"), now)
        last_day = monthrange(selected.year, selected.month)[1]
        result = upcoming_calendar(
            today=selected, window_days=last_day,
            session_factory=ns["SessionLocal"],
        )
        # Selecting a day filters the event list rather than scrolling to it.
        day_value = request.args.get("day")
        selected_day = None
        if day_value:
            try:
                candidate = date.fromisoformat(day_value)
            except (TypeError, ValueError):
                abort(400, "Invalid selected day")
            if candidate.year != selected.year or candidate.month != selected.month:
                abort(400, "Selected day must be within the displayed month")
            selected_day = candidate
        visible_days = [day for day in result["days"]
                        if day["iso"] == selected_day.isoformat()] if selected_day else result["days"]
        visible_count = sum(len(day["events"]) for day in visible_days)
        weeks = []
        row = [None] * selected.weekday()
        for day in result["days"]:
            row.append(day)
            if len(row) == 7:
                weeks.append(row)
                row = []
        if row:
            weeks.append(row + [None] * (7 - len(row)))
        prev_month = _shift_month(selected, -1)
        next_month = _shift_month(selected, 1)
        return render_template(
            "vault_calendar.html",
            calendar=result,
            visible_days=visible_days,
            visible_count=visible_count,
            selected_day=selected_day,
            weeks=weeks,
            selected_month=selected,
            month_heading=selected.strftime("%B %Y"),
            previous_month=prev_month.isoformat() if prev_month else None,
            next_month=next_month.isoformat() if next_month else None,
        )

    def calendar_event_detail(event_date, slug):
        event = _get_event_for_day(event_date, slug, ns["SessionLocal"])
        return render_template("vault_calendar_event.html", event=event,
                               calendar_actions=_calendar_actions(event))

    def calendar_event_ics(event_date, slug):
        event = _get_event_for_day(event_date, slug, ns["SessionLocal"])
        return Response(_event_ics(event), mimetype="text/calendar",
                        headers={"Content-Disposition": "attachment; filename=litefeet-event.ics",
                                 "Cache-Control": "private, no-store"})

    app.add_url_rule(
        "/calendar/events/<event_date>/<slug>/calendar.ics",
        endpoint="vault_calendar_event_ics", view_func=calendar_event_ics,
        methods=["GET"],
    )

    app.add_url_rule(
        "/calendar/events/<event_date>/<slug>",
        endpoint="vault_calendar_event_detail",
        view_func=calendar_event_detail,
        methods=["GET"],
    )

    # The legacy compatibility layer registered /calendar as a placeholder.
    # Replace its view, preserving the existing URL and endpoint for bookmarks.
    if "legacy_calendar" not in app.view_functions:
        raise RuntimeError("Expected legacy /calendar route to exist")
    app.view_functions["legacy_calendar"] = full_calendar
