from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import AccountStatus, User
from audit.models import AuditLog
from audit.services import record_audit_event

from .forms import ConversationForm, MessageForm
from .models import (
    Conversation,
    ConversationParticipant,
    Message,
    MessageRead,
    UserBlock,
)


def is_member(user):
    return (
        user.is_authenticated
        and user.is_active
        and user.account_status == AccountStatus.MEMBER
    )


def get_active_participation(user, conversation):
    if not user.is_authenticated:
        return None

    return ConversationParticipant.objects.filter(
        conversation=conversation,
        user=user,
        left_at__isnull=True,
    ).first()


def can_view_conversation(user, conversation):
    return get_active_participation(user, conversation) is not None


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


def conversation_has_block(request_user, conversation):
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


def conversation_values(conversation):
    return {
        "conversation_id": conversation.pk,
        "participants": list(
            conversation.participants.filter(
                left_at__isnull=True,
            ).values_list(
                "user__username",
                flat=True,
            )
        ),
        "created_at": conversation.created_at.isoformat(),
    }


def participant_values(participant):
    return {
        "conversation_id": participant.conversation_id,
        "user": str(participant.user),
        "joined_at": participant.joined_at.isoformat(),
        "left_at": (
            participant.left_at.isoformat()
            if participant.left_at
            else None
        ),
    }


def message_values(message):
    return {
        "message_id": message.pk,
        "conversation_id": message.conversation_id,
        "sender": str(message.sender),
        "delivery_status": message.delivery_status,
        "created_at": message.created_at.isoformat(),
    }


def block_values(block):
    return {
        "blocker": str(block.blocker),
        "blocked": str(block.blocked),
        "created_at": block.created_at.isoformat(),
    }


@login_required
def conversation_list(request):
    if not is_member(request.user):
        return HttpResponseForbidden()

    conversations = Conversation.objects.filter(
        participants__user=request.user,
        participants__left_at__isnull=True,
    ).prefetch_related(
        "participants__user",
    ).distinct()

    return render(
        request,
        "messaging/conversation_list.html",
        {
            "conversations": conversations,
        },
    )


@login_required
def conversation_detail(request, conversation_id):
    if not is_member(request.user):
        return HttpResponseForbidden()

    conversation = get_object_or_404(
        Conversation.objects.prefetch_related(
            "participants__user",
        ),
        pk=conversation_id,
    )

    if not can_view_conversation(request.user, conversation):
        return HttpResponseForbidden()

    visible_messages = conversation.messages.filter(
        delivery_status=Message.DeliveryStatus.SENT,
    ).select_related(
        "sender",
    )

    unread_messages = visible_messages.exclude(
        sender=request.user,
    ).exclude(
        read_records__user=request.user,
    )

    MessageRead.objects.bulk_create(
        [
            MessageRead(
                message=message,
                user=request.user,
            )
            for message in unread_messages
        ],
        ignore_conflicts=True,
    )

    blocked_user_ids = set(
        UserBlock.objects.filter(
            blocker=request.user,
        ).values_list(
            "blocked_id",
            flat=True,
        )
    )

    message_form = MessageForm()

    return render(
        request,
        "messaging/conversation_detail.html",
        {
            "conversation": conversation,
            "visible_messages": visible_messages,
            "message_form": message_form,
            "blocked_user_ids": blocked_user_ids,
        },
    )


@login_required
def conversation_create(request):
    if not is_member(request.user):
        return HttpResponseForbidden()

    if request.method == "POST":
        form = ConversationForm(
            request.POST,
            current_user=request.user,
        )

        if form.is_valid():
            selected_users = form.cleaned_data["participants"]

            conversation = Conversation.objects.create()

            ConversationParticipant.objects.create(
                conversation=conversation,
                user=request.user,
            )

            for user in selected_users:
                ConversationParticipant.objects.create(
                    conversation=conversation,
                    user=user,
                )

            record_audit_event(
                actor=request.user,
                request=request,
                action=AuditLog.Action.CREATE,
                target_type=conversation._meta.verbose_name,
                target_id=conversation.pk,
                target_label=str(conversation),
                new_value=conversation_values(conversation),
                source=AuditLog.Source.WEB_APP,
                method=AuditLog.Method.MANUAL,
            )

            return redirect(
                "messaging:conversation_detail",
                conversation_id=conversation.pk,
            )
    else:
        form = ConversationForm(
            current_user=request.user,
        )

    return render(
        request,
        "messaging/conversation_form.html",
        {
            "form": form,
        },
    )


@login_required
@require_POST
def send_message(request, conversation_id):
    if not is_member(request.user):
        return HttpResponseForbidden()

    conversation = get_object_or_404(
        Conversation,
        pk=conversation_id,
    )

    if not can_view_conversation(request.user, conversation):
        return HttpResponseForbidden()

    form = MessageForm(request.POST)

    if form.is_valid():
        message = form.save(commit=False)
        message.conversation = conversation
        message.sender = request.user

        if conversation_has_block(request.user, conversation):
            message.delivery_status = Message.DeliveryStatus.BLOCKED
        else:
            message.delivery_status = Message.DeliveryStatus.SENT

        message.save()

        record_audit_event(
            actor=request.user,
            request=request,
            action=AuditLog.Action.CREATE,
            target_type=message._meta.verbose_name,
            target_id=message.pk,
            target_label=str(message),
            new_value=message_values(message),
            source=AuditLog.Source.WEB_APP,
            method=AuditLog.Method.MANUAL,
        )

        if message.delivery_status == Message.DeliveryStatus.BLOCKED:
            messages.error(
                request,
                "Sorry, this user is unavailable.",
            )

            return redirect(
                "messaging:conversation_detail",
                conversation_id=conversation.pk,
            )

        conversation.save()

    return redirect(
        "messaging:conversation_detail",
        conversation_id=conversation.pk,
    )


@login_required
@require_POST
def leave_conversation(request, conversation_id):
    if not is_member(request.user):
        return HttpResponseForbidden()

    conversation = get_object_or_404(
        Conversation,
        pk=conversation_id,
    )

    participation = get_active_participation(
        request.user,
        conversation,
    )

    if participation is None:
        return HttpResponseForbidden()

    old_value = participant_values(participation)

    participation.left_at = timezone.now()
    participation.save(
        update_fields=["left_at"],
    )

    record_audit_event(
        actor=request.user,
        request=request,
        action=AuditLog.Action.UPDATE,
        target_type=participation._meta.verbose_name,
        target_id=participation.pk,
        target_label=str(participation),
        old_value=old_value,
        new_value=participant_values(participation),
        source=AuditLog.Source.WEB_APP,
        method=AuditLog.Method.MANUAL,
    )

    return redirect(
        "messaging:conversation_list",
    )


@login_required
@require_POST
def block_user(request, user_id):
    if not is_member(request.user):
        return HttpResponseForbidden()

    blocked_user = get_object_or_404(
        User,
        pk=user_id,
        account_status=AccountStatus.MEMBER,
        is_active=True,
    )

    if blocked_user.pk == request.user.pk:
        return HttpResponseForbidden()

    block, created = UserBlock.objects.get_or_create(
        blocker=request.user,
        blocked=blocked_user,
    )

    if created:
        record_audit_event(
            actor=request.user,
            request=request,
            action=AuditLog.Action.CREATE,
            target_type=block._meta.verbose_name,
            target_id=block.pk,
            target_label=str(block),
            new_value=block_values(block),
            source=AuditLog.Source.WEB_APP,
            method=AuditLog.Method.MANUAL,
        )

    return redirect(
        "messaging:conversation_list",
    )


@login_required
@require_POST
def unblock_user(request, user_id):
    if not is_member(request.user):
        return HttpResponseForbidden()

    block = UserBlock.objects.filter(
        blocker=request.user,
        blocked_id=user_id,
    ).first()

    if block is not None:
        old_value = block_values(block)

        target_id = block.pk
        target_label = str(block)
        target_type = block._meta.verbose_name

        block.delete()

        record_audit_event(
            actor=request.user,
            request=request,
            action=AuditLog.Action.DELETE,
            target_type=target_type,
            target_id=target_id,
            target_label=target_label,
            old_value=old_value,
            source=AuditLog.Source.WEB_APP,
            method=AuditLog.Method.MANUAL,
        )

    return redirect(
        "messaging:conversation_list",
    )