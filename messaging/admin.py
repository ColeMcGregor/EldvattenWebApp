from django.contrib import admin

from audit.models import AuditLog
from audit.services import record_audit_event

from .models import (
    Conversation,
    ConversationParticipant,
    Message,
    MessageRead,
    UserBlock,
)


def get_audit_values(obj):
    if isinstance(obj, Message):
        return {
            "conversation": str(obj.conversation),
            "conversation_id": obj.conversation_id,
            "sender": str(obj.sender),
            "delivery_status": obj.delivery_status,
            "created_at": (
                obj.created_at.isoformat()
                if obj.created_at
                else None
            ),
        }

    values = {}
    skipped_fields = {"id", "created_at", "updated_at"}

    for field in obj._meta.fields:
        if field.name in skipped_fields:
            continue

        value = getattr(obj, field.name)

        if field.is_relation and value is not None:
            values[field.name] = str(value)
        elif hasattr(value, "isoformat"):
            values[field.name] = value.isoformat()
        else:
            values[field.name] = value

    return values


class AuditedMessagingAdmin(admin.ModelAdmin):
    def save_model(self, request, obj, form, change):
        old_value = None

        if change:
            old_obj = type(obj).objects.get(pk=obj.pk)
            old_value = get_audit_values(old_obj)

        super().save_model(request, obj, form, change)

        record_audit_event(
            actor=request.user,
            request=request,
            action=(
                AuditLog.Action.UPDATE
                if change
                else AuditLog.Action.CREATE
            ),
            target_type=obj._meta.verbose_name,
            target_id=obj.pk,
            target_label=str(obj),
            old_value=old_value,
            new_value=get_audit_values(obj),
            source=AuditLog.Source.ADMIN,
            method=AuditLog.Method.MANUAL,
        )

    def delete_model(self, request, obj):
        old_value = get_audit_values(obj)

        target_id = obj.pk
        target_label = str(obj)
        target_type = obj._meta.verbose_name

        super().delete_model(request, obj)

        record_audit_event(
            actor=request.user,
            request=request,
            action=AuditLog.Action.DELETE,
            target_type=target_type,
            target_id=target_id,
            target_label=target_label,
            old_value=old_value,
            source=AuditLog.Source.ADMIN,
            method=AuditLog.Method.MANUAL,
        )


@admin.register(Conversation)
class ConversationAdmin(AuditedMessagingAdmin):
    list_display = (
        "id",
        "created_at",
        "updated_at",
    )

    ordering = (
        "-updated_at",
    )


@admin.register(ConversationParticipant)
class ConversationParticipantAdmin(AuditedMessagingAdmin):
    list_display = (
        "conversation",
        "user",
        "joined_at",
        "left_at",
    )

    list_filter = (
        "joined_at",
        "left_at",
    )

    search_fields = (
        "user__username",
        "user__display_name",
    )


@admin.register(Message)
class MessageAdmin(AuditedMessagingAdmin):
    list_display = (
        "sender",
        "conversation",
        "delivery_status",
        "created_at",
    )

    list_filter = (
        "delivery_status",
        "created_at",
    )

    search_fields = (
        "sender__username",
        "sender__display_name",
        "body",
    )

    ordering = (
        "created_at",
    )


@admin.register(MessageRead)
class MessageReadAdmin(AuditedMessagingAdmin):
    list_display = (
        "message",
        "user",
        "read_at",
    )

    list_filter = (
        "read_at",
    )

    search_fields = (
        "user__username",
        "user__display_name",
    )


@admin.register(UserBlock)
class UserBlockAdmin(AuditedMessagingAdmin):
    list_display = (
        "blocker",
        "blocked",
        "created_at",
    )

    list_filter = (
        "created_at",
    )

    search_fields = (
        "blocker__username",
        "blocker__display_name",
        "blocked__username",
        "blocked__display_name",
    )