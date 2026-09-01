from django.db import transaction
from django.db.models import Q
from django.urls import reverse

from notifications.models import Notification
from notifications.services import create_notifications

from .models import (
    Message,
    UserBlock,
)


def users_are_blocked(user_a, user_b):
    return UserBlock.objects.filter(
        Q(
            blocker=user_a,
            blocked=user_b,
        )
        | Q(
            blocker=user_b,
            blocked=user_a,
        )
    ).exists()


def conversation_has_block(
    request_user,
    conversation,
):
    other_user_ids = conversation.participants.filter(
        left_at__isnull=True,
    ).exclude(
        user=request_user,
    ).values_list(
        "user_id",
        flat=True,
    )

    return UserBlock.objects.filter(
        Q(
            blocker=request_user,
            blocked_id__in=other_user_ids,
        )
        | Q(
            blocker_id__in=other_user_ids,
            blocked=request_user,
        )
    ).exists()


def get_message_recipients(
    *,
    conversation,
    sender,
):
    return (
        conversation.participants.filter(
            left_at__isnull=True,
        )
        .exclude(
            user=sender,
        )
        .select_related(
            "user",
        )
    )


@transaction.atomic
def send_conversation_message(
    *,
    conversation,
    sender,
    body,
):
    message = Message(
        conversation=conversation,
        sender=sender,
        body=body,
    )

    if conversation_has_block(
        sender,
        conversation,
    ):
        message.delivery_status = (
            Message.DeliveryStatus.BLOCKED
        )
    else:
        message.delivery_status = (
            Message.DeliveryStatus.SENT
        )

    message.full_clean()
    message.save()

    if (
        message.delivery_status
        == Message.DeliveryStatus.BLOCKED
    ):
        return message

    recipients = [
        participant.user
        for participant in get_message_recipients(
            conversation=conversation,
            sender=sender,
        )
    ]

    if recipients:
        sender_name = (
            sender.display_name
            or sender.get_username()
        )

        create_notifications(
            recipients=recipients,
            notification_type=Notification.Type.MESSAGE,
            title=f"New message from {sender_name}",
            message="You received a new message.",
            source_type="Message",
            source_id=message.id,
            target_url=reverse(
                "messaging:conversation_detail",
                args=[
                    conversation.id,
                ],
            ),
        )

    conversation.save()

    return message