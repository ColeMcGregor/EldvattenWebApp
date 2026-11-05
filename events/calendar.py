import calendar
from datetime import date, datetime, time, timedelta
from types import SimpleNamespace

from django.utils import timezone


def selected_event_month(query_parameters, now):
    today = timezone.localtime(now).date()
    first_current_month = today.replace(day=1)

    try:
        year = int(query_parameters.get("year", today.year))
        month = int(query_parameters.get("month", today.month))
        if not 1 <= year <= 9998:
            raise ValueError
        selected = date(year, month, 1)
    except (TypeError, ValueError):
        selected = first_current_month

    if selected < first_current_month:
        selected = first_current_month

    if selected.month == 12:
        next_month = date(selected.year + 1, 1, 1)
    else:
        next_month = date(selected.year, selected.month + 1, 1)

    if selected == first_current_month:
        previous_month = None
    else:
        previous_month = selected - timedelta(days=1)
        previous_month = previous_month.replace(day=1)

    current_timezone = timezone.get_current_timezone()

    return {
        "year": selected.year,
        "month": selected.month,
        "month_name": calendar.month_name[selected.month],
        "first_day": selected,
        "previous_month": previous_month,
        "next_month": next_month,
        "range_start": timezone.make_aware(
            datetime.combine(selected, time.min),
            current_timezone,
        ),
        "range_end": timezone.make_aware(
            datetime.combine(next_month, time.min),
            current_timezone,
        ),
    }


def event_calendar_weeks(month_selection, events, now):
    first_day = month_selection["first_day"]
    today = timezone.localtime(now).date()
    events_by_date = {}

    for event in events:
        local_start = timezone.localtime(event.start_at).date()
        local_end_at = timezone.localtime(event.end_at)
        if event.end_at > event.start_at:
            local_end_at -= timedelta(microseconds=1)
        local_end = local_end_at.date()

        day = max(local_start, first_day)
        while day <= local_end and day < month_selection["next_month"]:
            if day >= today:
                events_by_date.setdefault(day, []).append(event)
            day += timedelta(days=1)

    calendar_weeks = calendar.Calendar(firstweekday=6).monthdatescalendar(
        first_day.year,
        first_day.month,
    )

    return [
        [
            SimpleNamespace(
                date=day,
                in_month=(day.month == first_day.month),
                is_today=(day == today),
                is_past=(day < today),
                events=events_by_date.get(day, []),
            )
            for day in week
        ]
        for week in calendar_weeks
    ]
