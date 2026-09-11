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


class Conversation(models.Model):
    class ConversationType(models.TextChoices):
        DIRECT = "DIRECT", "People"
        GROUP = "GROUP", "Group"

    conversation_type = models.CharField(
        max_length=20,
        choices=ConversationType.choices,
        default=ConversationType.DIRECT,
    )

    title = models.CharField(
        max_length=150,
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
            "-updated_at",
        ]

    def clean(self):
        if (
            self.conversation_type
            == self.ConversationType.GROUP
            and not self.title.strip()
        ):
            raise ValidationError(
                {
                    "title": (
                        "A group conversation must have a title."
                    )
                }
            )

    def __str__(self):
        if (
            self.conversation_type
            == self.ConversationType.GROUP
            and self.title
        ):
            return self.title

        return f"Conversation {self.pk}"


class ConversationParticipant(models.Model):
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="participants",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="conversation_participations",
    )

    joined_at = models.DateTimeField(
        auto_now_add=True,
    )

    left_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "conversation",
                    "user",
                ],
                name="unique_conversation_participant",
            ),
        ]

    def __str__(self):
        return (
            f"{self.user} in conversation "
            f"{self.conversation_id}"
        )


class ConversationTarget(models.Model):
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="targets",
    )

    citizenship_class = models.ForeignKey(
        CitizenshipClass,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="conversation_targets",
    )

    social_rank = models.ForeignKey(
        SocialRank,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="conversation_targets",
    )

    office = models.ForeignKey(
        Office,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="conversation_targets",
    )

    chapter = models.ForeignKey(
        Chapter,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="conversation_targets",
    )

    household = models.ForeignKey(
        Household,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="conversation_targets",
    )

    governance_body = models.ForeignKey(
        GovernanceBody,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="conversation_targets",
    )

    order = models.ForeignKey(
        Order,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="conversation_targets",
    )

    order_rank = models.ForeignKey(
        OrderRank,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="conversation_targets",
    )

    community_group = models.ForeignKey(
        CommunityGroup,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="conversation_targets",
    )

    household_leadership_type = models.ForeignKey(
        HouseholdLeadershipType,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="conversation_targets",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    def clean(self):
        target_fields = [
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
                (
                    "A conversation target must contain "
                    "at least one selector."
                )
            )

    def __str__(self):
        return (
            f"Target for conversation "
            f"{self.conversation_id}"
        )


class ConversationUserState(models.Model):
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="user_states",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="conversation_states",
    )

    is_muted = models.BooleanField(
        default=False,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "conversation",
                    "user",
                ],
                name="unique_conversation_user_state",
            ),
        ]

    def __str__(self):
        return (
            f"{self.user} state for conversation "
            f"{self.conversation_id}"
        )


class Message(models.Model):
    class DeliveryStatus(models.TextChoices):
        SENT = "SENT", "Sent"
        BLOCKED = "BLOCKED", "Blocked"

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="sent_messages",
    )

    body = models.TextField()

    delivery_status = models.CharField(
        max_length=20,
        choices=DeliveryStatus.choices,
        default=DeliveryStatus.SENT,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = [
            "created_at",
        ]

    def __str__(self):
        return (
            f"Message from {self.sender} "
            f"at {self.created_at}"
        )


class MessageRead(models.Model):
    message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        related_name="read_records",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="message_reads",
    )

    read_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "message",
                    "user",
                ],
                name="unique_message_read",
            ),
        ]

    def __str__(self):
        return (
            f"{self.user} read message "
            f"{self.message_id}"
        )


class UserBlock(models.Model):
    blocker = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="blocked_users",
    )

    blocked = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="blocked_by_users",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "blocker",
                    "blocked",
                ],
                name="unique_user_block",
            ),
        ]

    def clean(self):
        if self.blocker_id == self.blocked_id:
            raise ValidationError(
                {
                    "blocked": (
                        "A user cannot block themselves."
                    )
                }
            )

    def __str__(self):
        return (
            f"{self.blocker} blocked "
            f"{self.blocked}"
        )