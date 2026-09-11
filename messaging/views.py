from django.contrib import messages
from django.contrib.auth.decorators import (
    login_required,
)
from django.db import transaction
from django.http import HttpResponseForbidden
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.utils import timezone
from django.views.decorators.http import (
    require_POST,
)

from accounts.models import AccountStatus, User
from audit.models import AuditLog
from audit.services import record_audit_event

from .forms import (
    ConversationForm,
    ConversationTargetFormSet,
    MessageForm,
)
from .models import (
    Conversation,
    ConversationParticipant,
    Message,
    MessageRead,
    UserBlock,
)
from .services import (
    get_accessible_conversations,
    get_active_participation,
    get_conversation_display_title,
    get_unread_message_count,
    get_visible_messages,
    send_conversation_message,
    set_conversation_muted,
    user_can_access_conversation,
    user_is_conversation_muted,
)


def is_member(user):
    return (
        user.is_authenticated
        and user.is_active
        and user.account_status
        == AccountStatus.MEMBER
    )


def can_view_conversation(
    user,
    conversation,
):
    return user_can_access_conversation(
        user,
        conversation,
    )


def conversation_target_values(
    conversation,
):
    targets = []

    for target in (
        conversation.targets
        .all()
        .order_by("id")
    ):
        targets.append(
            {
                "citizenship_class": (
                    str(
                        target.citizenship_class
                    )
                    if target.citizenship_class
                    else None
                ),
                "social_rank": (
                    str(target.social_rank)
                    if target.social_rank
                    else None
                ),
                "office": (
                    str(target.office)
                    if target.office
                    else None
                ),
                "chapter": (
                    str(target.chapter)
                    if target.chapter
                    else None
                ),
                "household": (
                    str(target.household)
                    if target.household
                    else None
                ),
                "governance_body": (
                    str(
                        target.governance_body
                    )
                    if target.governance_body
                    else None
                ),
                "order": (
                    str(target.order)
                    if target.order
                    else None
                ),
                "order_rank": (
                    str(target.order_rank)
                    if target.order_rank
                    else None
                ),
                "community_group": (
                    str(
                        target.community_group
                    )
                    if target.community_group
                    else None
                ),
                (
                    "household_"
                    "leadership_type"
                ): (
                    str(
                        target
                        .household_leadership_type
                    )
                    if (
                        target
                        .household_leadership_type
                    )
                    else None
                ),
            }
        )

    return targets


def conversation_values(
    conversation,
):
    return {
        "conversation_id": conversation.pk,
        "conversation_type": (
            conversation.conversation_type
        ),
        "title": conversation.title,
        "participants": list(
            conversation.participants
            .filter(
                left_at__isnull=True,
            )
            .values_list(
                "user__username",
                flat=True,
            )
        ),
        "targets": (
            conversation_target_values(
                conversation
            )
        ),
        "created_at": (
            conversation.created_at
            .isoformat()
        ),
    }


def participant_values(participant):
    return {
        "conversation_id": (
            participant.conversation_id
        ),
        "user": str(participant.user),
        "joined_at": (
            participant.joined_at
            .isoformat()
        ),
        "left_at": (
            participant.left_at
            .isoformat()
            if participant.left_at
            else None
        ),
    }


def message_values(message):
    return {
        "message_id": message.pk,
        "conversation_id": (
            message.conversation_id
        ),
        "sender": str(message.sender),
        "delivery_status": (
            message.delivery_status
        ),
        "created_at": (
            message.created_at.isoformat()
        ),
    }


def block_values(block):
    return {
        "blocker": str(block.blocker),
        "blocked": str(block.blocked),
        "created_at": (
            block.created_at.isoformat()
        ),
    }


def prepare_conversations_for_display(
    conversations,
    user,
):
    prepared_conversations = []

    for conversation in conversations:
        conversation.display_title = (
            get_conversation_display_title(
                conversation,
                user,
            )
        )

        conversation.unread_count = (
            get_unread_message_count(
                conversation=conversation,
                user=user,
            )
        )

        conversation.is_muted_for_user = (
            user_is_conversation_muted(
                conversation=conversation,
                user=user,
            )
        )

        conversation.latest_visible_message = (
            get_visible_messages(
                conversation=conversation,
                user=user,
            )
            .order_by("-created_at")
            .first()
        )

        prepared_conversations.append(
            conversation
        )

    return prepared_conversations


def get_messages_page_context(user):
    conversations = (
        get_accessible_conversations(
            user
        )
    )

    conversations = (
        prepare_conversations_for_display(
            conversations,
            user,
        )
    )

    conversation = Conversation()

    conversation_form = ConversationForm(
        current_user=user,
    )

    conversation_target_formset = (
        ConversationTargetFormSet(
            instance=conversation,
            prefix="targets",
        )
    )

    return {
        "conversations": conversations,
        "conversation_form": conversation_form,
        "conversation_target_formset": (
            conversation_target_formset
        ),
    }


@login_required
def conversation_list(request):
    if not is_member(request.user):
        return HttpResponseForbidden()

    context = get_messages_page_context(
        request.user
    )

    return render(
        request,
        "messaging/conversation_list.html",
        context,
    )


@login_required
def conversation_detail(
    request,
    conversation_id,
):
    if not is_member(request.user):
        return HttpResponseForbidden()

    conversation = get_object_or_404(
        Conversation.objects
        .prefetch_related(
            "participants__user",
            "targets",
        ),
        pk=conversation_id,
    )

    if not can_view_conversation(
        request.user,
        conversation,
    ):
        return HttpResponseForbidden()

    visible_messages = (
        get_visible_messages(
            conversation=conversation,
            user=request.user,
        )
    )

    unread_messages = (
        visible_messages
        .filter(
            delivery_status=(
                Message.DeliveryStatus.SENT
            ),
        )
        .exclude(
            sender=request.user,
        )
        .exclude(
            read_records__user=(
                request.user
            ),
        )
        .distinct()
    )

    MessageRead.objects.bulk_create(
        [
            MessageRead(
                message=message,
                user=request.user,
            )
            for message
            in unread_messages
        ],
        ignore_conflicts=True,
    )

    blocked_user_ids = set(
        UserBlock.objects
        .filter(
            blocker=request.user,
        )
        .values_list(
            "blocked_id",
            flat=True,
        )
    )

    conversation.display_title = (
        get_conversation_display_title(
            conversation,
            request.user,
        )
    )

    conversation.is_muted_for_user = (
        user_is_conversation_muted(
            conversation=conversation,
            user=request.user,
        )
    )

    message_form = MessageForm()

    context = get_messages_page_context(
        request.user
    )

    context.update(
        {
            "conversation": conversation,
            "visible_messages": (
                visible_messages
            ),
            "message_form": message_form,
            "blocked_user_ids": (
                blocked_user_ids
            ),
        }
    )

    return render(
        request,
        "messaging/conversation_detail.html",
        context,
    )


@login_required
def conversation_create(request):
    if not is_member(request.user):
        return HttpResponseForbidden()

    if request.method != "POST":
        return redirect(
            "messaging:conversation_list"
        )

    conversation = Conversation()

    form = ConversationForm(
        request.POST,
        current_user=request.user,
    )

    target_formset = (
        ConversationTargetFormSet(
            request.POST,
            instance=conversation,
            prefix="targets",
        )
    )

    if form.is_valid():
        conversation_type = (
            form.cleaned_data[
                "conversation_type"
            ]
        )

        conversation.conversation_type = (
            conversation_type
        )

        conversation.title = (
            form.cleaned_data[
                "title"
            ]
        )

        if (
            conversation_type
            == Conversation
            .ConversationType
            .DIRECT
        ):
            with transaction.atomic():
                conversation.full_clean()
                conversation.save()

                ConversationParticipant.objects.create(
                    conversation=conversation,
                    user=request.user,
                )

                selected_users = (
                    form.cleaned_data[
                        "participants"
                    ]
                )

                for user in selected_users:
                    ConversationParticipant.objects.create(
                        conversation=(
                            conversation
                        ),
                        user=user,
                    )

            record_audit_event(
                actor=request.user,
                request=request,
                action=AuditLog.Action.CREATE,
                target_type=(
                    conversation
                    ._meta
                    .verbose_name
                ),
                target_id=conversation.pk,
                target_label=str(
                    conversation
                ),
                new_value=(
                    conversation_values(
                        conversation
                    )
                ),
                source=(
                    AuditLog.Source.WEB_APP
                ),
                method=(
                    AuditLog.Method.MANUAL
                ),
            )

            return redirect(
                (
                    "messaging:"
                    "conversation_detail"
                ),
                conversation_id=(
                    conversation.pk
                ),
            )

        if (
            conversation_type
            == Conversation
            .ConversationType
            .GROUP
            and target_formset.is_valid()
        ):
            with transaction.atomic():
                conversation.full_clean()
                conversation.save()

                target_formset.instance = (
                    conversation
                )

                target_formset.save()

            record_audit_event(
                actor=request.user,
                request=request,
                action=AuditLog.Action.CREATE,
                target_type=(
                    conversation
                    ._meta
                    .verbose_name
                ),
                target_id=conversation.pk,
                target_label=str(
                    conversation
                ),
                new_value=(
                    conversation_values(
                        conversation
                    )
                ),
                source=(
                    AuditLog.Source.WEB_APP
                ),
                method=(
                    AuditLog.Method.MANUAL
                ),
            )

            if can_view_conversation(
                request.user,
                conversation,
            ):
                return redirect(
                    (
                        "messaging:"
                        "conversation_detail"
                    ),
                    conversation_id=(
                        conversation.pk
                    ),
                )

            return redirect(
                (
                    "messaging:"
                    "conversation_list"
                ),
            )

    messages.error(
        request,
        "The conversation could not be created.",
    )

    return redirect(
        "messaging:conversation_list"
    )


@login_required
@require_POST
def send_message(
    request,
    conversation_id,
):
    if not is_member(request.user):
        return HttpResponseForbidden()

    conversation = get_object_or_404(
        Conversation.objects
        .prefetch_related(
            "targets",
        ),
        pk=conversation_id,
    )

    if not can_view_conversation(
        request.user,
        conversation,
    ):
        return HttpResponseForbidden()

    form = MessageForm(
        request.POST
    )

    if form.is_valid():
        message = (
            send_conversation_message(
                conversation=conversation,
                sender=request.user,
                body=(
                    form.cleaned_data[
                        "body"
                    ]
                ),
            )
        )

        record_audit_event(
            actor=request.user,
            request=request,
            action=AuditLog.Action.CREATE,
            target_type=(
                message
                ._meta
                .verbose_name
            ),
            target_id=message.pk,
            target_label=str(message),
            new_value=message_values(
                message
            ),
            source=(
                AuditLog.Source.WEB_APP
            ),
            method=(
                AuditLog.Method.MANUAL
            ),
        )

        if (
            message.delivery_status
            == Message
            .DeliveryStatus
            .BLOCKED
        ):
            messages.error(
                request,
                (
                    "Messaging is unavailable "
                    "for this conversation."
                ),
            )

    return redirect(
        "messaging:conversation_detail",
        conversation_id=conversation.pk,
    )


@login_required
@require_POST
def leave_conversation(
    request,
    conversation_id,
):
    if not is_member(request.user):
        return HttpResponseForbidden()

    conversation = get_object_or_404(
        Conversation,
        pk=conversation_id,
    )

    if (
        conversation.conversation_type
        != Conversation
        .ConversationType
        .DIRECT
    ):
        return HttpResponseForbidden()

    participation = (
        get_active_participation(
            request.user,
            conversation,
        )
    )

    if participation is None:
        return HttpResponseForbidden()

    old_value = participant_values(
        participation
    )

    participation.left_at = (
        timezone.now()
    )

    participation.save(
        update_fields=[
            "left_at",
        ],
    )

    record_audit_event(
        actor=request.user,
        request=request,
        action=AuditLog.Action.UPDATE,
        target_type=(
            participation
            ._meta
            .verbose_name
        ),
        target_id=participation.pk,
        target_label=str(
            participation
        ),
        old_value=old_value,
        new_value=participant_values(
            participation
        ),
        source=AuditLog.Source.WEB_APP,
        method=AuditLog.Method.MANUAL,
    )

    return redirect(
        "messaging:conversation_list",
    )


@login_required
@require_POST
def mute_conversation(
    request,
    conversation_id,
):
    if not is_member(request.user):
        return HttpResponseForbidden()

    conversation = get_object_or_404(
        Conversation.objects
        .prefetch_related(
            "targets",
        ),
        pk=conversation_id,
    )

    if not can_view_conversation(
        request.user,
        conversation,
    ):
        return HttpResponseForbidden()

    set_conversation_muted(
        conversation=conversation,
        user=request.user,
        is_muted=True,
    )

    return redirect(
        "messaging:conversation_detail",
        conversation_id=conversation.pk,
    )


@login_required
@require_POST
def unmute_conversation(
    request,
    conversation_id,
):
    if not is_member(request.user):
        return HttpResponseForbidden()

    conversation = get_object_or_404(
        Conversation.objects
        .prefetch_related(
            "targets",
        ),
        pk=conversation_id,
    )

    if not can_view_conversation(
        request.user,
        conversation,
    ):
        return HttpResponseForbidden()

    set_conversation_muted(
        conversation=conversation,
        user=request.user,
        is_muted=False,
    )

    return redirect(
        "messaging:conversation_detail",
        conversation_id=conversation.pk,
    )


@login_required
@require_POST
def block_user(
    request,
    user_id,
):
    if not is_member(request.user):
        return HttpResponseForbidden()

    blocked_user = get_object_or_404(
        User,
        pk=user_id,
        account_status=(
            AccountStatus.MEMBER
        ),
        is_active=True,
    )

    if (
        blocked_user.pk
        == request.user.pk
    ):
        return HttpResponseForbidden()

    block, created = (
        UserBlock.objects
        .get_or_create(
            blocker=request.user,
            blocked=blocked_user,
        )
    )

    if created:
        record_audit_event(
            actor=request.user,
            request=request,
            action=AuditLog.Action.CREATE,
            target_type=(
                block
                ._meta
                .verbose_name
            ),
            target_id=block.pk,
            target_label=str(block),
            new_value=block_values(
                block
            ),
            source=(
                AuditLog.Source.WEB_APP
            ),
            method=(
                AuditLog.Method.MANUAL
            ),
        )

    return redirect(
        "messaging:conversation_list",
    )


@login_required
@require_POST
def unblock_user(
    request,
    user_id,
):
    if not is_member(request.user):
        return HttpResponseForbidden()

    block = (
        UserBlock.objects
        .filter(
            blocker=request.user,
            blocked_id=user_id,
        )
        .first()
    )

    if block is not None:
        old_value = block_values(
            block
        )

        target_id = block.pk
        target_label = str(block)
        target_type = (
            block
            ._meta
            .verbose_name
        )

        block.delete()

        record_audit_event(
            actor=request.user,
            request=request,
            action=AuditLog.Action.DELETE,
            target_type=target_type,
            target_id=target_id,
            target_label=target_label,
            old_value=old_value,
            source=(
                AuditLog.Source.WEB_APP
            ),
            method=(
                AuditLog.Method.MANUAL
            ),
        )

    return redirect(
        "messaging:conversation_list",
    )