from django.db import transaction
from django.db.models import Q
from django.urls import reverse

from accounts.models import (
    AccountStatus,
    User,
)
from notifications.models import Notification
from notifications.services import (
    create_notifications,
)
from organization.models import (
    CitizenshipRecord,
    GovernanceMembership,
    GroupMembership,
    HouseholdLeadership,
    HouseholdMembership,
    OrderMembership,
    UserOffice,
    UserSocialRank,
)

from .models import (
    Conversation,
    ConversationParticipant,
    ConversationTarget,
    ConversationUserState,
    Message,
    UserBlock,
)


def users_are_blocked(
    user_a,
    user_b,
):
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


def get_active_participation(
    user,
    conversation,
):
    if not user.is_authenticated:
        return None

    return (
        ConversationParticipant.objects
        .filter(
            conversation=conversation,
            user=user,
            left_at__isnull=True,
        )
        .first()
    )


def resolve_conversation_target(
    target,
):
    user_ids = set(
        User.objects
        .filter(
            account_status=AccountStatus.MEMBER,
            is_active=True,
        )
        .values_list(
            "id",
            flat=True,
        )
    )

    if (
        target.citizenship_class_id
        is not None
    ):
        matching_ids = set(
            CitizenshipRecord.objects
            .filter(
                citizenship_class_id=(
                    target.citizenship_class_id
                ),
                ended_at__isnull=True,
            )
            .values_list(
                "user_id",
                flat=True,
            )
        )

        user_ids &= matching_ids

    if target.social_rank_id is not None:
        matching_ids = set(
            UserSocialRank.objects
            .filter(
                social_rank_id=(
                    target.social_rank_id
                ),
                ended_at__isnull=True,
            )
            .values_list(
                "user_id",
                flat=True,
            )
        )

        user_ids &= matching_ids

    if target.office_id is not None:
        office_records = (
            UserOffice.objects
            .filter(
                office_id=target.office_id,
                ended_at__isnull=True,
            )
        )

        if target.chapter_id is not None:
            office_records = (
                office_records.filter(
                    chapter_id=(
                        target.chapter_id
                    ),
                )
            )

        matching_ids = set(
            office_records.values_list(
                "user_id",
                flat=True,
            )
        )

        user_ids &= matching_ids

    if target.chapter_id is not None:
        matching_ids = set(
            CitizenshipRecord.objects
            .filter(
                chapter_id=target.chapter_id,
                ended_at__isnull=True,
            )
            .values_list(
                "user_id",
                flat=True,
            )
        )

        user_ids &= matching_ids

    if target.household_id is not None:
        matching_ids = set(
            HouseholdMembership.objects
            .filter(
                household_id=(
                    target.household_id
                ),
                ended_at__isnull=True,
            )
            .values_list(
                "user_id",
                flat=True,
            )
        )

        user_ids &= matching_ids

    if (
        target.governance_body_id
        is not None
    ):
        matching_ids = set(
            GovernanceMembership.objects
            .filter(
                governance_body_id=(
                    target.governance_body_id
                ),
                ended_at__isnull=True,
            )
            .values_list(
                "user_id",
                flat=True,
            )
        )

        user_ids &= matching_ids

    if target.order_id is not None:
        order_records = (
            OrderMembership.objects
            .filter(
                order_id=target.order_id,
                ended_at__isnull=True,
            )
        )

        if target.order_rank_id is not None:
            order_records = (
                order_records.filter(
                    order_rank_id=(
                        target.order_rank_id
                    ),
                )
            )

        matching_ids = set(
            order_records.values_list(
                "user_id",
                flat=True,
            )
        )

        user_ids &= matching_ids

    elif target.order_rank_id is not None:
        matching_ids = set(
            OrderMembership.objects
            .filter(
                order_rank_id=(
                    target.order_rank_id
                ),
                ended_at__isnull=True,
            )
            .values_list(
                "user_id",
                flat=True,
            )
        )

        user_ids &= matching_ids

    if (
        target.community_group_id
        is not None
    ):
        matching_ids = set(
            GroupMembership.objects
            .filter(
                community_group_id=(
                    target.community_group_id
                ),
                ended_at__isnull=True,
            )
            .values_list(
                "user_id",
                flat=True,
            )
        )

        user_ids &= matching_ids

    if (
        target.household_leadership_type_id
        is not None
    ):
        leadership_records = (
            HouseholdLeadership.objects
            .filter(
                leadership_type_id=(
                    target
                    .household_leadership_type_id
                ),
                ended_at__isnull=True,
            )
        )

        if target.household_id is not None:
            leadership_records = (
                leadership_records.filter(
                    household_id=(
                        target.household_id
                    ),
                )
            )

        matching_ids = set(
            leadership_records.values_list(
                "user_id",
                flat=True,
            )
        )

        user_ids &= matching_ids

    return user_ids


def resolve_conversation_targets(
    conversation,
):
    resolved_user_ids = set()

    for target in conversation.targets.all():
        resolved_user_ids.update(
            resolve_conversation_target(
                target
            )
        )

    return resolved_user_ids


def user_can_access_conversation(
    user,
    conversation,
):
    if not user.is_authenticated:
        return False

    if not user.is_active:
        return False

    if (
        user.account_status
        != AccountStatus.MEMBER
    ):
        return False

    if (
        conversation.conversation_type
        == Conversation.ConversationType.DIRECT
    ):
        return (
            get_active_participation(
                user,
                conversation,
            )
            is not None
        )

    if (
        conversation.conversation_type
        == Conversation.ConversationType.GROUP
    ):
        return (
            user.id
            in resolve_conversation_targets(
                conversation
            )
        )

    return False


def get_accessible_conversations(user):
    if not user.is_authenticated:
        return Conversation.objects.none()

    if not user.is_active:
        return Conversation.objects.none()

    if (
        user.account_status
        != AccountStatus.MEMBER
    ):
        return Conversation.objects.none()

    direct_conversation_ids = set(
        ConversationParticipant.objects
        .filter(
            user=user,
            left_at__isnull=True,
            conversation__conversation_type=(
                Conversation
                .ConversationType
                .DIRECT
            ),
        )
        .values_list(
            "conversation_id",
            flat=True,
        )
    )

    group_conversation_ids = set()

    group_conversations = (
        Conversation.objects
        .filter(
            conversation_type=(
                Conversation
                .ConversationType
                .GROUP
            )
        )
        .prefetch_related(
            "targets",
        )
    )

    for conversation in group_conversations:
        if (
            user.id
            in resolve_conversation_targets(
                conversation
            )
        ):
            group_conversation_ids.add(
                conversation.id
            )

    accessible_ids = (
        direct_conversation_ids
        | group_conversation_ids
    )

    if not accessible_ids:
        return Conversation.objects.none()

    return (
        Conversation.objects
        .filter(
            id__in=accessible_ids,
        )
        .prefetch_related(
            "participants__user",
            "targets",
        )
        .distinct()
        .order_by(
            "-updated_at",
        )
    )


def conversation_has_block(
    request_user,
    conversation,
):
    if (
        conversation.conversation_type
        == Conversation.ConversationType.GROUP
    ):
        return False

    other_user_ids = (
        conversation.participants
        .filter(
            left_at__isnull=True,
        )
        .exclude(
            user=request_user,
        )
        .values_list(
            "user_id",
            flat=True,
        )
    )

    return UserBlock.objects.filter(
        Q(
            blocker=request_user,
            blocked_id__in=(
                other_user_ids
            ),
        )
        | Q(
            blocker_id__in=(
                other_user_ids
            ),
            blocked=request_user,
        )
    ).exists()


def get_message_recipient_users(
    *,
    conversation,
    sender,
):
    if (
        conversation.conversation_type
        == Conversation.ConversationType.DIRECT
    ):
        recipient_ids = (
            conversation.participants
            .filter(
                left_at__isnull=True,
            )
            .exclude(
                user=sender,
            )
            .values_list(
                "user_id",
                flat=True,
            )
        )

        return (
            User.objects
            .filter(
                id__in=recipient_ids,
                account_status=(
                    AccountStatus.MEMBER
                ),
                is_active=True,
            )
            .order_by(
                "id",
            )
        )

    if (
        conversation.conversation_type
        == Conversation.ConversationType.GROUP
    ):
        recipient_ids = (
            resolve_conversation_targets(
                conversation
            )
        )

        recipient_ids.discard(
            sender.id
        )

        return (
            User.objects
            .filter(
                id__in=recipient_ids,
                account_status=(
                    AccountStatus.MEMBER
                ),
                is_active=True,
            )
            .order_by(
                "id",
            )
        )

    return User.objects.none()


def get_visible_messages(
    *,
    conversation,
    user,
):
    return (
        conversation.messages
        .filter(
            Q(
                delivery_status=(
                    Message
                    .DeliveryStatus
                    .SENT
                )
            )
            | Q(
                delivery_status=(
                    Message
                    .DeliveryStatus
                    .BLOCKED
                ),
                sender=user,
            )
        )
        .select_related(
            "sender",
        )
        .order_by(
            "created_at",
        )
    )


def get_unread_message_count(
    *,
    conversation,
    user,
):
    return (
        conversation.messages
        .filter(
            delivery_status=(
                Message.DeliveryStatus.SENT
            ),
        )
        .exclude(
            sender=user,
        )
        .exclude(
            read_records__user=user,
        )
        .distinct()
        .count()
    )


def get_conversation_display_title(
    conversation,
    user,
):
    if (
        conversation.conversation_type
        == Conversation.ConversationType.GROUP
    ):
        return (
            conversation.title
            or "Group conversation"
        )

    other_users = []

    for participant in (
        conversation.participants.all()
    ):
        if participant.user_id == user.id:
            continue

        participant_user = participant.user

        other_users.append(
            participant_user.display_name
            or participant_user.get_username()
        )

    if not other_users:
        return "Direct conversation"

    return ", ".join(
        other_users
    )


def user_is_conversation_muted(
    *,
    conversation,
    user,
):
    return (
        ConversationUserState.objects
        .filter(
            conversation=conversation,
            user=user,
            is_muted=True,
        )
        .exists()
    )


def set_conversation_muted(
    *,
    conversation,
    user,
    is_muted,
):
    state, _ = (
        ConversationUserState.objects
        .get_or_create(
            conversation=conversation,
            user=user,
        )
    )

    state.is_muted = is_muted

    state.save(
        update_fields=[
            "is_muted",
            "updated_at",
        ]
    )

    return state


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

    recipient_users = list(
        get_message_recipient_users(
            conversation=conversation,
            sender=sender,
        )
    )

    if recipient_users:
        muted_user_ids = set(
            ConversationUserState.objects
            .filter(
                conversation=conversation,
                is_muted=True,
            )
            .values_list(
                "user_id",
                flat=True,
            )
        )

        notification_recipients = [
            recipient
            for recipient
            in recipient_users
            if recipient.id
            not in muted_user_ids
        ]

        if notification_recipients:
            sender_name = (
                sender.display_name
                or sender.get_username()
            )

            create_notifications(
                recipients=(
                    notification_recipients
                ),
                notification_type=(
                    Notification.Type.MESSAGE
                ),
                title=(
                    f"New message from "
                    f"{sender_name}"
                ),
                message=(
                    "You received a new message."
                ),
                source_type="Message",
                source_id=message.id,
                target_url=reverse(
                    (
                        "messaging:"
                        "conversation_detail"
                    ),
                    args=[
                        conversation.id,
                    ],
                ),
            )

    conversation.save(
        update_fields=[
            "updated_at",
        ]
    )

    return message