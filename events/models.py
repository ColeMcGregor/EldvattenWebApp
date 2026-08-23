from django.conf import settings
from django.db import models
from django.db.models import F, Q


class Event(models.Model):
    class Visibility(models.TextChoices):
        PUBLIC = "PUBLIC", "Public"
        MEMBERS = "MEMBERS", "Members"

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    start_at = models.DateTimeField()
    end_at = models.DateTimeField()

    location = models.CharField(
        max_length=255,
        blank=True,
    )

    organizer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="organized_events",
    )

    visibility = models.CharField(
        max_length=20,
        choices=Visibility.choices,
        default=Visibility.MEMBERS,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["start_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(end_at__gte=F("start_at")),
                name="event_end_not_before_start",
            ),
        ]

    def __str__(self):
        return self.title


class EventParticipation(models.Model):
    class RSVPStatus(models.TextChoices):
        GOING = "GOING", "Going"
        MAYBE = "MAYBE", "Maybe"
        NOT_GOING = "NOT_GOING", "Not Going"

    class AttendanceStatus(models.TextChoices):
        UNKNOWN = "UNKNOWN", "Unknown"
        ATTENDED = "ATTENDED", "Attended"
        ABSENT = "ABSENT", "Absent"

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="participations",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="event_participations",
    )

    rsvp_status = models.CharField(
        max_length=20,
        choices=RSVPStatus.choices,
        blank=True,
    )

    attendance_status = models.CharField(
        max_length=20,
        choices=AttendanceStatus.choices,
        default=AttendanceStatus.UNKNOWN,
    )

    rsvp_updated_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    attendance_recorded_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["event", "user"],
                name="unique_event_participation",
            ),
        ]
        permissions = [
            (
                "record_attendance",
                "Can record event attendance",
            ),
        ]

    def __str__(self):
        return f"{self.user} - {self.event}"