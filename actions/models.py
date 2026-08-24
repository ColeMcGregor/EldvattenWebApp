from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from community.models import Post
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


class Action(models.Model):
    title = models.CharField(max_length=200)

    instructions = models.TextField(
        blank=True,
    )

    external_url = models.URLField(
        blank=True,
    )

    deadline = models.DateTimeField(
        blank=True,
        null=True,
    )

    is_required = models.BooleanField(
        default=False,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_actions",
    )

    linked_posts = models.ManyToManyField(
        Post,
        blank=True,
        related_name="linked_actions",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = [
            "deadline",
            "-created_at",
        ]

    def __str__(self):
        return self.title


class ActionTarget(models.Model):
    action = models.ForeignKey(
        Action,
        on_delete=models.CASCADE,
        related_name="targets",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="action_targets",
    )

    citizenship_class = models.ForeignKey(
        CitizenshipClass,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="action_targets",
    )

    social_rank = models.ForeignKey(
        SocialRank,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="action_targets",
    )

    office = models.ForeignKey(
        Office,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="action_targets",
    )

    chapter = models.ForeignKey(
        Chapter,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="action_targets",
    )

    household = models.ForeignKey(
        Household,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="action_targets",
    )

    governance_body = models.ForeignKey(
        GovernanceBody,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="action_targets",
    )

    order = models.ForeignKey(
        Order,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="action_targets",
    )

    order_rank = models.ForeignKey(
        OrderRank,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="action_targets",
    )

    community_group = models.ForeignKey(
        CommunityGroup,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="action_targets",
    )

    household_leadership_type = models.ForeignKey(
        HouseholdLeadershipType,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="action_targets",
    )

    created_at = models.DateTimeField(auto_now_add=True)

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
                "An action target must contain at least one selector."
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
                    "A specific user target cannot be combined with organizational selectors."
                )

    def __str__(self):
        return f"Target for {self.action}"


class ActionAssignment(models.Model):
    class Status(models.TextChoices):
        NOT_STARTED = "NOT_STARTED", "Not Started"
        OPENED = "OPENED", "Opened"
        COMPLETED = "COMPLETED", "Completed"

    action = models.ForeignKey(
        Action,
        on_delete=models.CASCADE,
        related_name="assignments",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="action_assignments",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NOT_STARTED,
    )

    opened_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    completed_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "action",
                    "user",
                ],
                name="unique_action_assignment",
            ),
        ]

    def clean(self):
        if self.status == self.Status.NOT_STARTED:
            if self.opened_at is not None or self.completed_at is not None:
                raise ValidationError(
                    "A not-started assignment cannot have opened or completed timestamps."
                )

        elif self.status == self.Status.OPENED:
            if self.opened_at is None:
                raise ValidationError(
                    "An opened assignment must have an opened timestamp."
                )

            if self.completed_at is not None:
                raise ValidationError(
                    "An opened assignment cannot have a completed timestamp."
                )

        elif self.status == self.Status.COMPLETED:
            if self.opened_at is None:
                raise ValidationError(
                    "A completed assignment must have an opened timestamp."
                )

            if self.completed_at is None:
                raise ValidationError(
                    "A completed assignment must have a completed timestamp."
                )

            if self.completed_at < self.opened_at:
                raise ValidationError(
                    "An assignment cannot be completed before it was opened."
                )

    def mark_opened(self):
        if self.status != self.Status.NOT_STARTED:
            return

        self.status = self.Status.OPENED
        self.opened_at = timezone.now()
        self.completed_at = None

        self.full_clean()
        self.save(
            update_fields=[
                "status",
                "opened_at",
                "completed_at",
            ]
        )

    def mark_completed(self):
        if self.status == self.Status.COMPLETED:
            return

        now = timezone.now()

        if self.opened_at is None:
            self.opened_at = now

        self.status = self.Status.COMPLETED
        self.completed_at = now

        self.full_clean()
        self.save(
            update_fields=[
                "status",
                "opened_at",
                "completed_at",
            ]
        )

    def __str__(self):
        return f"{self.user} - {self.action}"