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


class Vote(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        OPEN = "OPEN", "Open"
        CLOSED = "CLOSED", "Closed"

    class ApprovalRule(models.TextChoices):
        SIMPLE_MAJORITY = "SIMPLE_MAJORITY", "Simple Majority"
        UNANIMOUS = "UNANIMOUS", "Unanimous"

    title = models.CharField(max_length=200)

    description = models.TextField(
        blank=True,
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )

    approval_rule = models.CharField(
        max_length=30,
        choices=ApprovalRule.choices,
        default=ApprovalRule.SIMPLE_MAJORITY,
    )

    is_anonymous = models.BooleanField(
        default=False,
    )

    requires_quorum = models.BooleanField(
        default=True,
    )

    quorum_numerator = models.PositiveIntegerField(
        default=2,
    )

    quorum_denominator = models.PositiveIntegerField(
        default=5,
    )

    requires_all_responses = models.BooleanField(
        default=False,
    )

    push_on_open = models.BooleanField(
        default=False,
    )

    opens_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    closes_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    opened_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    closed_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_votes",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = [
            "-created_at",
        ]

    def clean(self):
        if self.quorum_denominator == 0:
            raise ValidationError(
                "The quorum denominator cannot be zero."
            )

        if self.quorum_numerator > self.quorum_denominator:
            raise ValidationError(
                "The quorum numerator cannot be greater than the denominator."
            )

        if (
            self.opens_at is not None
            and self.closes_at is not None
            and self.closes_at <= self.opens_at
        ):
            raise ValidationError(
                "The vote must close after it opens."
            )

        if self.pk:
            existing = Vote.objects.filter(
                pk=self.pk,
            ).first()

            if (
                existing is not None
                and existing.status != self.Status.DRAFT
                and existing.is_anonymous != self.is_anonymous
            ):
                raise ValidationError(
                    "Anonymity cannot be changed after a vote has opened."
                )

        if self.status == self.Status.DRAFT:
            if self.opened_at is not None or self.closed_at is not None:
                raise ValidationError(
                    "A draft vote cannot have opened or closed timestamps."
                )

        elif self.status == self.Status.OPEN:
            if self.opened_at is None:
                raise ValidationError(
                    "An open vote must have an opened timestamp."
                )

            if self.closed_at is not None:
                raise ValidationError(
                    "An open vote cannot have a closed timestamp."
                )

        elif self.status == self.Status.CLOSED:
            if self.opened_at is None:
                raise ValidationError(
                    "A closed vote must have an opened timestamp."
                )

            if self.closed_at is None:
                raise ValidationError(
                    "A closed vote must have a closed timestamp."
                )

            if self.closed_at < self.opened_at:
                raise ValidationError(
                    "A vote cannot close before it opened."
                )

    def __str__(self):
        return self.title


class VoteOption(models.Model):
    vote = models.ForeignKey(
        Vote,
        on_delete=models.CASCADE,
        related_name="options",
    )

    label = models.CharField(max_length=200)

    sort_order = models.PositiveIntegerField(
        default=0,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = [
            "sort_order",
            "id",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "vote",
                    "label",
                ],
                name="unique_vote_option_label",
            ),
        ]

    def __str__(self):
        return f"{self.vote}: {self.label}"


class VoteEligibilityTarget(models.Model):
    vote = models.ForeignKey(
        Vote,
        on_delete=models.CASCADE,
        related_name="eligibility_targets",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="vote_eligibility_targets",
    )

    citizenship_class = models.ForeignKey(
        CitizenshipClass,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="vote_eligibility_targets",
    )

    social_rank = models.ForeignKey(
        SocialRank,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="vote_eligibility_targets",
    )

    office = models.ForeignKey(
        Office,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="vote_eligibility_targets",
    )

    chapter = models.ForeignKey(
        Chapter,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="vote_eligibility_targets",
    )

    household = models.ForeignKey(
        Household,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="vote_eligibility_targets",
    )

    governance_body = models.ForeignKey(
        GovernanceBody,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="vote_eligibility_targets",
    )

    order = models.ForeignKey(
        Order,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="vote_eligibility_targets",
    )

    order_rank = models.ForeignKey(
        OrderRank,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="vote_eligibility_targets",
    )

    community_group = models.ForeignKey(
        CommunityGroup,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="vote_eligibility_targets",
    )

    household_leadership_type = models.ForeignKey(
        HouseholdLeadershipType,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="vote_eligibility_targets",
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
                "A vote eligibility target must contain at least one selector."
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
        return f"Eligibility target for {self.vote}"


class VoteEligibleUser(models.Model):
    vote = models.ForeignKey(
        Vote,
        on_delete=models.CASCADE,
        related_name="eligible_users",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="vote_eligibilities",
    )

    has_responded = models.BooleanField(
        default=False,
    )

    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "vote",
                    "user",
                ],
                name="unique_vote_eligible_user",
            ),
        ]

    def __str__(self):
        return f"{self.user} - {self.vote}"


class VoteResponse(models.Model):
    eligibility = models.OneToOneField(
        VoteEligibleUser,
        on_delete=models.CASCADE,
        related_name="response",
        blank=True,
        null=True,
    )

    option = models.ForeignKey(
        VoteOption,
        on_delete=models.PROTECT,
        related_name="responses",
    )

    submitted_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    updated_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    @property
    def vote(self):
        return self.option.vote

    def clean(self):
        if self.option_id is None:
            return

        vote = self.option.vote

        if vote.is_anonymous:
            if self.eligibility_id is not None:
                raise ValidationError(
                    "An anonymous vote response cannot identify the voter."
                )

            if (
                self.submitted_at is not None
                or self.updated_at is not None
            ):
                raise ValidationError(
                    "An anonymous vote response cannot store submission timestamps."
                )

        else:
            if self.eligibility_id is None:
                raise ValidationError(
                    "A non-anonymous vote response must identify the voter."
                )

            if self.eligibility.vote_id != vote.id:
                raise ValidationError(
                    "The voter eligibility does not belong to this vote."
                )

            if self.submitted_at is None:
                raise ValidationError(
                    "A non-anonymous vote response must have a submission timestamp."
                )

    def __str__(self):
        if self.eligibility_id is None:
            return f"Anonymous response - {self.vote}"

        return f"{self.eligibility.user} - {self.vote}"


class VoteComment(models.Model):
    vote = models.ForeignKey(
        Vote,
        on_delete=models.CASCADE,
        related_name="comments",
    )

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="vote_comments",
    )

    body = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = [
            "created_at",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "vote",
                    "author",
                ],
                name="unique_vote_comment_per_user",
            ),
        ]

    def clean(self):
        if not VoteEligibleUser.objects.filter(
            vote=self.vote,
            user=self.author,
        ).exists():
            raise ValidationError(
                "Only an eligible voter can comment on this vote."
            )

    def __str__(self):
        return f"{self.author} - {self.vote}"