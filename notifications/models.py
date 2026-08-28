from django.conf import settings
from django.db import models


class Notification(models.Model):
    class Type(models.TextChoices):
        ACTION = "ACTION", "Action"
        VOTE = "VOTE", "Vote"
        EVENT = "EVENT", "Event"
        MESSAGE = "MESSAGE", "Message"
        COMMUNITY = "COMMUNITY", "Community"
        ACCOUNT = "ACCOUNT", "Account"
        SYSTEM = "SYSTEM", "System"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )

    notification_type = models.CharField(
        max_length=30,
        choices=Type.choices,
    )

    title = models.CharField(
        max_length=200,
    )

    message = models.TextField(
        blank=True,
    )

    source_type = models.CharField(
        max_length=100,
        blank=True,
    )

    source_id = models.CharField(
        max_length=100,
        blank=True,
    )

    target_url = models.CharField(
        max_length=500,
        blank=True,
    )

    push_requested = models.BooleanField(
        default=False,
    )

    is_read = models.BooleanField(
        default=False,
    )

    read_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = [
            "-created_at",
        ]

        indexes = [
            models.Index(
                fields=[
                    "user",
                    "is_read",
                    "-created_at",
                ],
                name="notification_user_read_idx",
            ),
            models.Index(
                fields=[
                    "source_type",
                    "source_id",
                ],
                name="notification_source_idx",
            ),
        ]

    def __str__(self):
        return f"{self.user} - {self.title}"


class PushSubscription(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="push_subscriptions",
    )

    endpoint = models.TextField(
        unique=True,
    )

    p256dh_key = models.TextField()

    auth_key = models.TextField()

    device_name = models.CharField(
        max_length=200,
        blank=True,
    )

    active = models.BooleanField(
        default=True,
    )

    paused_until = models.DateTimeField(
        blank=True,
        null=True,
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

        indexes = [
            models.Index(
                fields=[
                    "user",
                    "active",
                ],
                name="push_user_active_idx",
            ),
        ]

    def __str__(self):
        return (
            f"{self.user} - "
            f"{self.device_name or 'Push device'}"
        )