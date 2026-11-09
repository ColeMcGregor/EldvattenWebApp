
from django.utils import timezone

from .models import Event


def active_public_events():
    return Event.objects.filter(
        visibility=Event.Visibility.PUBLIC,
        status=Event.Status.ACTIVE,
    )


def upcoming_public_events(*, now=None, limit=5):
    if now is None:
        now = timezone.now()

    events = (
        active_public_events()
        .filter(end_at__gt=now)
        .order_by("start_at", "id")
    )

    if limit is not None:
        events = events[:limit]

    return events
