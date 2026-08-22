from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q


class CitizenshipClass(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    is_assignable = models.BooleanField(
        default=True,
        verbose_name="Assignable",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Citizenship class"
        verbose_name_plural = "Citizenship classes"

    def __str__(self):
        return self.name


class SocialRank(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    is_assignable = models.BooleanField(
        default=True,
        verbose_name="Assignable",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class Office(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    is_assignable = models.BooleanField(
        default=True,
        verbose_name="Assignable",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class ChapterStatus(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    allows_new_citizens = models.BooleanField(default=True)
    is_selectable = models.BooleanField(
        default=True,
        verbose_name="Selectable",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Chapter status"
        verbose_name_plural = "Chapter statuses"

    def __str__(self):
        return self.name


class Chapter(models.Model):
    name = models.CharField(max_length=150, unique=True)
    description = models.TextField(blank=True)
    status = models.ForeignKey(
        ChapterStatus,
        on_delete=models.PROTECT,
        related_name="chapters",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class Household(models.Model):
    name = models.CharField(max_length=150, unique=True)
    description = models.TextField(blank=True)
    is_assignable = models.BooleanField(
        default=True,
        verbose_name="Assignable",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class GovernanceBody(models.Model):
    name = models.CharField(max_length=150, unique=True)
    description = models.TextField(blank=True)
    is_assignable = models.BooleanField(
        default=True,
        verbose_name="Assignable",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Governance body"
        verbose_name_plural = "Governance bodies"

    def __str__(self):
        return self.name


class Order(models.Model):
    name = models.CharField(max_length=150, unique=True)
    description = models.TextField(blank=True)
    uses_ranks = models.BooleanField(default=False)
    is_assignable = models.BooleanField(
        default=True,
        verbose_name="Assignable",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class OrderRank(models.Model):
    name = models.CharField(max_length=100, unique=True)
    rank_order = models.PositiveIntegerField(default=0)
    is_assignable = models.BooleanField(
        default=True,
        verbose_name="Assignable",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["rank_order", "name"]

    def __str__(self):
        return self.name


class CommunityGroup(models.Model):
    name = models.CharField(max_length=150, unique=True)
    description = models.TextField(blank=True)
    is_assignable = models.BooleanField(
        default=True,
        verbose_name="Assignable",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class HouseholdLeadershipType(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    is_assignable = models.BooleanField(
        default=True,
        verbose_name="Assignable",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class HistoricalAssignment(models.Model):
    started_at = models.DateField()
    ended_at = models.DateField(blank=True, null=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class CitizenshipRecord(HistoricalAssignment):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="citizenship_records",
    )
    citizenship_class = models.ForeignKey(
        CitizenshipClass,
        on_delete=models.PROTECT,
        related_name="citizenship_records",
    )
    chapter = models.ForeignKey(
        Chapter,
        on_delete=models.PROTECT,
        related_name="citizenship_records",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(ended_at__isnull=True),
                name="one_current_citizenship_per_user",
            ),
        ]

    def __str__(self):
        return f"{self.user} - {self.citizenship_class} - {self.chapter}"


class UserSocialRank(HistoricalAssignment):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="social_rank_records",
    )
    social_rank = models.ForeignKey(
        SocialRank,
        on_delete=models.PROTECT,
        related_name="user_records",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(ended_at__isnull=True),
                name="one_current_social_rank_per_user",
            ),
        ]

    def __str__(self):
        return f"{self.user} - {self.social_rank}"


class UserOffice(HistoricalAssignment):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="office_records",
    )
    office = models.ForeignKey(
        Office,
        on_delete=models.PROTECT,
        related_name="user_records",
    )
    chapter = models.ForeignKey(
        Chapter,
        on_delete=models.PROTECT,
        related_name="office_records",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "office", "chapter"],
                condition=Q(ended_at__isnull=True),
                name="unique_current_user_office",
            ),
        ]

    def __str__(self):
        return f"{self.user} - {self.office} - {self.chapter}"


class HouseholdMembership(HistoricalAssignment):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="household_memberships",
    )
    household = models.ForeignKey(
        Household,
        on_delete=models.PROTECT,
        related_name="memberships",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "household"],
                condition=Q(ended_at__isnull=True),
                name="unique_current_household_membership",
            ),
        ]

    def __str__(self):
        return f"{self.user} - {self.household}"


class HouseholdLeadership(HistoricalAssignment):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="household_leadership_records",
    )
    household = models.ForeignKey(
        Household,
        on_delete=models.PROTECT,
        related_name="leadership_records",
    )
    leadership_type = models.ForeignKey(
        HouseholdLeadershipType,
        on_delete=models.PROTECT,
        related_name="leadership_records",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "household", "leadership_type"],
                condition=Q(ended_at__isnull=True),
                name="unique_current_household_leadership",
            ),
        ]

    def __str__(self):
        return f"{self.user} - {self.leadership_type} - {self.household}"


class GovernanceMembership(HistoricalAssignment):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="governance_memberships",
    )
    governance_body = models.ForeignKey(
        GovernanceBody,
        on_delete=models.PROTECT,
        related_name="memberships",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "governance_body"],
                condition=Q(ended_at__isnull=True),
                name="unique_current_governance_membership",
            ),
        ]

    def __str__(self):
        return f"{self.user} - {self.governance_body}"


class OrderMembership(HistoricalAssignment):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="order_memberships",
    )
    order = models.ForeignKey(
        Order,
        on_delete=models.PROTECT,
        related_name="memberships",
    )
    order_rank = models.ForeignKey(
        OrderRank,
        on_delete=models.PROTECT,
        related_name="memberships",
        blank=True,
        null=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "order"],
                condition=Q(ended_at__isnull=True),
                name="unique_current_order_membership",
            ),
        ]

    def clean(self):
        super().clean()

        if self.order.uses_ranks and not self.order_rank:
            raise ValidationError(
                {"order_rank": "A rank is required for this Order."}
            )

        if not self.order.uses_ranks and self.order_rank:
            raise ValidationError(
                {"order_rank": "This Order does not use ranks."}
            )

    def __str__(self):
        if self.order_rank:
            return f"{self.user} - {self.order} - {self.order_rank}"

        return f"{self.user} - {self.order}"


class GroupMembership(HistoricalAssignment):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="community_group_memberships",
    )
    community_group = models.ForeignKey(
        CommunityGroup,
        on_delete=models.PROTECT,
        related_name="memberships",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "community_group"],
                condition=Q(ended_at__isnull=True),
                name="unique_current_group_membership",
            ),
        ]

    def __str__(self):
        return f"{self.user} - {self.community_group}"


class InitiateSponsorship(HistoricalAssignment):
    class SponsorType(models.TextChoices):
        PRIMARY = "PRIMARY", "Primary"
        SECONDARY = "SECONDARY", "Secondary"

    initiate = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="initiate_sponsorships",
    )
    sponsor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="sponsorships_given",
    )
    sponsor_type = models.CharField(
        max_length=20,
        choices=SponsorType.choices,
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=~Q(initiate=F("sponsor")),
                name="prevent_self_sponsorship",
            ),
            models.UniqueConstraint(
                fields=["initiate", "sponsor_type"],
                condition=Q(ended_at__isnull=True),
                name="one_current_sponsor_per_type",
            ),
        ]

    def __str__(self):
        return f"{self.initiate} - {self.get_sponsor_type_display()}: {self.sponsor}"