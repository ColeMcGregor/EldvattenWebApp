from pathlib import Path

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

from .storage import private_resource_storage


class Resource(models.Model):
    class ResourceType(models.TextChoices):
        FILE = "FILE", "File"
        LINK = "LINK", "Link"

    class Visibility(models.TextChoices):
        MEMBERS = "MEMBERS", "All Members"
        CUSTOM = "CUSTOM", "Custom"

    title = models.CharField(
        max_length=255,
    )

    description = models.TextField(
        blank=True,
    )

    resource_type = models.CharField(
        max_length=20,
        choices=ResourceType.choices,
    )

    file = models.FileField(
        upload_to="resources/",
        storage=private_resource_storage,
        blank=True,
        null=True,
    )

    external_url = models.URLField(
        blank=True,
    )

    visibility = models.CharField(
        max_length=20,
        choices=Visibility.choices,
        default=Visibility.MEMBERS,
    )

    sort_order = models.PositiveIntegerField(
        default=0,
    )

    is_active = models.BooleanField(
        default=True,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_resources",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = (
            "sort_order",
            "title",
        )

        permissions = (
            (
                "manage_resources",
                "Can manage resources",
            ),
        )

    def __str__(self):
        return self.title

    def clean(self):
        super().clean()

        errors = {}

        if self.resource_type == self.ResourceType.FILE:
            if not self.file:
                errors["file"] = (
                    "A file is required for a file resource."
                )

            if self.external_url:
                errors["external_url"] = (
                    "A file resource cannot have an external URL."
                )

        elif self.resource_type == self.ResourceType.LINK:
            if not self.external_url:
                errors["external_url"] = (
                    "An external URL is required for a link resource."
                )

            if self.file:
                errors["file"] = (
                    "A link resource cannot have a file."
                )

        if errors:
            raise ValidationError(errors)

    @property
    def filename(self):
        if not self.file:
            return ""

        return Path(
            self.file.name
        ).name


class ResourceTarget(models.Model):
    class Effect(models.TextChoices):
        INCLUDE = "INCLUDE", "Include"
        EXCLUDE = "EXCLUDE", "Exclude"

    resource = models.ForeignKey(
        Resource,
        on_delete=models.CASCADE,
        related_name="targets",
    )

    effect = models.CharField(
        max_length=20,
        choices=Effect.choices,
        default=Effect.INCLUDE,
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="resource_targets",
        blank=True,
        null=True,
    )

    citizenship_class = models.ForeignKey(
        CitizenshipClass,
        on_delete=models.CASCADE,
        related_name="resource_targets",
        blank=True,
        null=True,
    )

    social_rank = models.ForeignKey(
        SocialRank,
        on_delete=models.CASCADE,
        related_name="resource_targets",
        blank=True,
        null=True,
    )

    office = models.ForeignKey(
        Office,
        on_delete=models.CASCADE,
        related_name="resource_targets",
        blank=True,
        null=True,
    )

    chapter = models.ForeignKey(
        Chapter,
        on_delete=models.CASCADE,
        related_name="resource_targets",
        blank=True,
        null=True,
    )

    household = models.ForeignKey(
        Household,
        on_delete=models.CASCADE,
        related_name="resource_targets",
        blank=True,
        null=True,
    )

    governance_body = models.ForeignKey(
        GovernanceBody,
        on_delete=models.CASCADE,
        related_name="resource_targets",
        blank=True,
        null=True,
    )

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="resource_targets",
        blank=True,
        null=True,
    )

    order_rank = models.ForeignKey(
        OrderRank,
        on_delete=models.CASCADE,
        related_name="resource_targets",
        blank=True,
        null=True,
    )

    community_group = models.ForeignKey(
        CommunityGroup,
        on_delete=models.CASCADE,
        related_name="resource_targets",
        blank=True,
        null=True,
    )

    household_leadership_type = models.ForeignKey(
        HouseholdLeadershipType,
        on_delete=models.CASCADE,
        related_name="resource_targets",
        blank=True,
        null=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = (
            "resource",
            "effect",
            "id",
        )

    def __str__(self):
        return (
            f"{self.resource} - "
            f"{self.get_effect_display()}"
        )

    def clean(self):
        super().clean()

        selectors = (
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
        )

        if not any(selectors):
            raise ValidationError(
                "A resource target must contain "
                "at least one selector."
            )

        organization_selectors = (
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
        )

        if (
            self.user is not None
            and any(organization_selectors)
        ):
            raise ValidationError(
                "A user target cannot be combined "
                "with organization selectors."
            )