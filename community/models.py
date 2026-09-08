from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

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


class Post(models.Model):
    class Visibility(models.TextChoices):
        ALL = "ALL", "All"
        GUESTS = "GUESTS", "Guests"
        MEMBERS = "MEMBERS", "Members"
        SELECTED_GROUPS = (
            "SELECTED_GROUPS",
            "Selected Groups",
        )

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="community_posts",
    )

    previous_version = models.OneToOneField(
        "self",
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="next_version",
    )

    body = models.TextField()

    visibility = models.CharField(
        max_length=20,
        choices=Visibility.choices,
        default=Visibility.MEMBERS,
    )

    is_official = models.BooleanField(
        default=False,
    )

    is_pinned = models.BooleanField(
        default=False,
    )

    is_locked = models.BooleanField(
        default=False,
    )

    is_deleted = models.BooleanField(
        default=False,
    )

    deleted_at = models.DateTimeField(
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

    def __str__(self):
        return (
            f"Post by {self.author} "
            f"at {self.created_at}"
        )


class PostTarget(models.Model):
    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name="targets",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="post_targets",
    )

    citizenship_class = models.ForeignKey(
        CitizenshipClass,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="post_targets",
    )

    social_rank = models.ForeignKey(
        SocialRank,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="post_targets",
    )

    office = models.ForeignKey(
        Office,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="post_targets",
    )

    chapter = models.ForeignKey(
        Chapter,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="post_targets",
    )

    household = models.ForeignKey(
        Household,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="post_targets",
    )

    governance_body = models.ForeignKey(
        GovernanceBody,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="post_targets",
    )

    order = models.ForeignKey(
        Order,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="post_targets",
    )

    order_rank = models.ForeignKey(
        OrderRank,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="post_targets",
    )

    community_group = models.ForeignKey(
        CommunityGroup,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="post_targets",
    )

    household_leadership_type = models.ForeignKey(
        HouseholdLeadershipType,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="post_targets",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

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
                "A post target must contain at least one selector."
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
        return f"Target for {self.post}"


class Comment(models.Model):
    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name="comments",
    )

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="community_comments",
    )

    body = models.TextField()

    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="replies",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = [
            "created_at",
        ]

    def clean(self):
        if self.parent is None:
            return

        if self.parent.post_id != self.post_id:
            raise ValidationError(
                {
                    "parent": (
                        "A reply must belong to the same post."
                    )
                }
            )

        if self.parent.parent_id is not None:
            raise ValidationError(
                {
                    "parent": (
                        "Replies can only be one level deep."
                    )
                }
            )

    def __str__(self):
        return (
            f"Comment by {self.author} "
            f"on post {self.post_id}"
        )