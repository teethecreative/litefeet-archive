"""Public event calendar, distinct from the historical archive timeline."""
from calendar import monthrange
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from flask import abort, render_template, request

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
        try:
            selected_day = date.fromisoformat(event_date)
        except (ValueError, TypeError):
            abort(404)
        calendar = upcoming_calendar(
            today=selected_day, window_days=1,
            session_factory=ns["SessionLocal"],
        )
        event = next(
            (item for item in calendar["events"] if event_slug(item["title"]) == slug),
            None,
        )
        if event is None:
            abort(404)
        return render_template("vault_calendar_event.html", event=event)

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
