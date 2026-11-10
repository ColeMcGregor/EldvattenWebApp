
from django.conf import settings
from django.db import models


class BugReport(models.Model):
    class Status(models.TextChoices):
        NEW = "NEW", "New"
        INVESTIGATING = "INVESTIGATING", "Investigating"
        RESOLVED = "RESOLVED", "Resolved"
        DUPLICATE = "DUPLICATE", "Duplicate"
        CLOSED = "CLOSED", "Closed"

    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="bug_reports",
        blank=True,
        null=True,
    )

    contact_email = models.EmailField(
        blank=True,
    )

    description = models.TextField()

    expected_behavior = models.TextField(
        blank=True,
    )

    steps_to_reproduce = models.TextField(
        blank=True,
    )

    page_url = models.URLField(
        max_length=2000,
        blank=True,
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NEW,
    )

    admin_notes = models.TextField(
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = [
            "-created_at",
        ]

    def __str__(self):
        return f"Bug Report #{self.pk}"


class SubmissionThrottle(models.Model):
    class Period(models.TextChoices):
        MINUTE = "MINUTE", "Minute"
        HOUR = "HOUR", "Hour"

    identifier = models.CharField(
        max_length=64,
    )

    period = models.CharField(
        max_length=10,
        choices=Period.choices,
    )

    submission_count = models.PositiveIntegerField(
        default=0,
    )

    window_started_at = models.DateTimeField()

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "identifier",
                    "period",
                ],
                name="unique_feedback_submission_throttle",
            ),
        ]

    def __str__(self):
        return (
            f"{self.period} submission quota "
            f"({self.pk})"
        )
