
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from community.views import forum_index
from events.calendar import event_calendar_weeks, selected_event_month
from events.queries import active_public_events, upcoming_public_events


def home(request):
    return render(
        request,
        "home.html",
        {
            "upcoming_events": upcoming_public_events(
                limit=4,
            ),
        },
    )


def about(request):
    return render(request, "about.html")


def calendar_view(request):
    now = timezone.now()
    selected_month = selected_event_month(request.GET, now)

    month_events = list(
        active_public_events()
        .filter(
            start_at__lt=selected_month["range_end"],
            end_at__gt=max(
                now,
                selected_month["range_start"],
            ),
        )
        .order_by("start_at", "id")
    )

    context = {
        "calendar_public": True,
        "calendar_year": selected_month["year"],
        "calendar_month": selected_month["month"],
        "calendar_month_name": selected_month["month_name"],
        "calendar_previous_month": selected_month["previous_month"],
        "calendar_next_month": selected_month["next_month"],
        "calendar_weekday_names": (
            "Sunday",
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
        ),
        "calendar_weeks": event_calendar_weeks(
            selected_month,
            month_events,
            now,
        ),
        "upcoming_events": upcoming_public_events(
            now=now,
            limit=10,
        ),
    }

    return render(
        request,
        "events/calendar.html",
        context,
    )


def tavern(request):
    return render(
        request,
        "tavern.html",
    )


@login_required
def tavern_main(request):
    return forum_index(request)


def contact(request):
    return render(
        request,
        "contact.html",
    )


def privacy(request):
    return render(
        request,
        "privacy.html",
    )
