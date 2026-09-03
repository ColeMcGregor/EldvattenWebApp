from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from organization.models import (
    Chapter,
    CitizenshipClass,
    CommunityGroup,
    GovernanceBody,
    Household,
    HouseholdLeadershipType,
    Office,
    Order,
    OrderRank,
    SocialRank,
)


class Event(models.Model):
    class Visibility(models.TextChoices):
        PUBLIC = "PUBLIC", "Public"
        MEMBERS = "MEMBERS", "Members"
        CUSTOM = "CUSTOM", "Custom"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        CANCELLED = "CANCELLED", "Cancelled"

    title = models.CharField(
        max_length=200,
    )

    description = models.TextField(
        blank=True,
    )

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

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = [
            "start_at",
        ]

        constraints = [
            models.CheckConstraint(
                condition=Q(
                    end_at__gte=F("start_at"),
                ),
                name="event_end_not_before_start",
            ),
        ]

    def __str__(self):
        return self.title


class EventTarget(models.Model):
    class Purpose(models.TextChoices):
        INVITATION = (
            "INVITATION",
            "Invitation",
        )

        VISIBILITY = (
            "VISIBILITY",
            "Visibility",
        )

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="targets",
    )

    purpose = models.CharField(
        max_length=20,
        choices=Purpose.choices,
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="event_targets",
    )

    citizenship_class = models.ForeignKey(
        CitizenshipClass,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="event_targets",
    )

    social_rank = models.ForeignKey(
        SocialRank,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="event_targets",
    )

    office = models.ForeignKey(
        Office,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="event_targets",
    )

    chapter = models.ForeignKey(
        Chapter,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="event_targets",
    )

    household = models.ForeignKey(
        Household,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="event_targets",
    )

    governance_body = models.ForeignKey(
        GovernanceBody,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="event_targets",
    )

    order = models.ForeignKey(
        Order,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="event_targets",
    )

    order_rank = models.ForeignKey(
        OrderRank,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="event_targets",
    )

    community_group = models.ForeignKey(
        CommunityGroup,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="event_targets",
    )

    household_leadership_type = models.ForeignKey(
        HouseholdLeadershipType,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="event_targets",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = [
            "purpose",
            "created_at",
        ]

    def clean(self):
        target_fields = [
            self.user,
            self.citizenship_class,
            self.social_rank,
            self.office,
            self.chapter,
            self.household,
            self.governance_body,
            self.order,
            self.order_rank,
            self.community_group,
            self.household_leadership_type,
        ]

        if not any(target_fields):
            raise ValidationError(
                "An event target must contain at least one selector."
            )

        if self.user is not None:
            other_fields = [
                self.citizenship_class,
                self.social_rank,
                self.office,
                self.chapter,
                self.household,
                self.governance_body,
                self.order,
                self.order_rank,
                self.community_group,
                self.household_leadership_type,
            ]

            if any(other_fields):
                raise ValidationError(
                    "A specific user target cannot be combined "
                    "with organizational selectors."
                )

    def __str__(self):
        return (
            f"{self.get_purpose_display()} target "
            f"for {self.event}"
        )


class EventInvitation(models.Model):
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="invitations",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="event_invitations",
    )

    is_active = models.BooleanField(
        default=True,
    )

    invited_at = models.DateTimeField(
        auto_now_add=True,
    )

    uninvited_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "event",
                    "user",
                ],
                name="unique_event_invitation",
            ),
        ]

    def clean(self):
        if (
            self.is_active
            and self.uninvited_at is not None
        ):
            raise ValidationError(
                "An active invitation cannot have "
                "an uninvited timestamp."
            )

        if (
            not self.is_active
            and self.uninvited_at is None
        ):
            raise ValidationError(
                "An inactive invitation must have "
                "an uninvited timestamp."
            )

    def deactivate(self):
        if not self.is_active:
            return

        self.is_active = False
        self.uninvited_at = timezone.now()

        self.full_clean()

        self.save(
            update_fields=[
                "is_active",
                "uninvited_at",
            ]
        )

    def reactivate(self):
        if self.is_active:
            return

        self.is_active = True
        self.uninvited_at = None

        self.full_clean()

        self.save(
            update_fields=[
                "is_active",
                "uninvited_at",
            ]
        )

    def __str__(self):
        return f"{self.user} - {self.event}"


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

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "event",
                    "user",
                ],
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