from django.contrib import admin

from audit.models import AuditLog
from audit.services import record_audit_event

from .models import Event, EventParticipation


class AuditedEventAdmin(admin.ModelAdmin):
    def get_audit_values(self, obj):
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

    def save_model(self, request, obj, form, change):
        old_value = None

        if change:
            old_obj = type(obj).objects.get(pk=obj.pk)
            old_value = self.get_audit_values(old_obj)

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
            new_value=self.get_audit_values(obj),
            source=AuditLog.Source.ADMIN,
            method=AuditLog.Method.MANUAL,
        )

    def delete_model(self, request, obj):
        old_value = self.get_audit_values(obj)
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


@admin.register(Event)
class EventAdmin(AuditedEventAdmin):
    list_display = (
        "title",
        "start_at",
        "end_at",
        "location",
        "organizer",
        "visibility",
    )

    list_filter = (
        "visibility",
        "start_at",
    )

    search_fields = (
        "title",
        "description",
        "location",
        "organizer__username",
        "organizer__display_name",
    )

    ordering = ("start_at",)


@admin.register(EventParticipation)
class EventParticipationAdmin(AuditedEventAdmin):
    list_display = (
        "user",
        "event",
        "rsvp_status",
        "attendance_status",
        "rsvp_updated_at",
        "attendance_recorded_at",
    )

    list_filter = (
        "rsvp_status",
        "attendance_status",
        "event",
    )

    search_fields = (
        "user__username",
        "user__display_name",
        "event__title",
    )