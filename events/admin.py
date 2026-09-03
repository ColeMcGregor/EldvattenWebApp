from django.contrib import admin

from audit.models import AuditLog
from audit.services import record_audit_event

from .models import (
    Event,
    EventInvitation,
    EventParticipation,
    EventTarget,
)
from .services import (
    material_event_changes,
    notify_event_cancelled,
    notify_event_updated,
    sync_event_invitations,
)


class AuditedEventAdmin(admin.ModelAdmin):
    def get_audit_values(self, obj):
        values = {}
        skipped_fields = {
            "id",
            "created_at",
            "updated_at",
        }

        for field in obj._meta.fields:
            if field.name in skipped_fields:
                continue

            value = getattr(
                obj,
                field.name,
            )

            if (
                field.is_relation
                and value is not None
            ):
                values[field.name] = str(value)

            elif hasattr(
                value,
                "isoformat",
            ):
                values[field.name] = (
                    value.isoformat()
                )

            else:
                values[field.name] = value

        return values

    def save_model(
        self,
        request,
        obj,
        form,
        change,
    ):
        old_value = None

        if change:
            old_obj = type(
                obj
            ).objects.get(
                pk=obj.pk
            )

            old_value = (
                self.get_audit_values(
                    old_obj
                )
            )

        super().save_model(
            request,
            obj,
            form,
            change,
        )

        new_value = (
            self.get_audit_values(
                obj
            )
        )

        obj._admin_old_audit_value = old_value
        obj._admin_new_audit_value = new_value
        obj._admin_was_change = change

        record_audit_event(
            actor=request.user,
            request=request,
            action=(
                AuditLog.Action.UPDATE
                if change
                else AuditLog.Action.CREATE
            ),
            target_type=(
                obj._meta.verbose_name
            ),
            target_id=obj.pk,
            target_label=str(obj),
            old_value=old_value,
            new_value=new_value,
            source=AuditLog.Source.ADMIN,
            method=AuditLog.Method.MANUAL,
        )

    def delete_model(
        self,
        request,
        obj,
    ):
        old_value = (
            self.get_audit_values(
                obj
            )
        )

        target_id = obj.pk
        target_label = str(obj)

        target_type = (
            obj._meta.verbose_name
        )

        super().delete_model(
            request,
            obj,
        )

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


class EventTargetInline(
    admin.StackedInline
):
    model = EventTarget

    extra = 1

    fields = (
        "purpose",
        "user",
        "citizenship_class",
        "social_rank",
        "office",
        "chapter",
        "household",
        "governance_body",
        "order",
        "order_rank",
        "community_group",
        "household_leadership_type",
    )


class EventInvitationInline(
    admin.TabularInline
):
    model = EventInvitation

    extra = 0

    fields = (
        "user",
        "is_active",
        "invited_at",
        "uninvited_at",
    )

    readonly_fields = (
        "user",
        "is_active",
        "invited_at",
        "uninvited_at",
    )

    can_delete = False

    def has_add_permission(
        self,
        request,
        obj=None,
    ):
        return False


@admin.register(Event)
class EventAdmin(AuditedEventAdmin):
    list_display = (
        "title",
        "start_at",
        "end_at",
        "location",
        "organizer",
        "visibility",
        "status",
    )

    list_filter = (
        "status",
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

    ordering = (
        "start_at",
    )

    inlines = (
        EventTargetInline,
        EventInvitationInline,
    )

    def save_related(
        self,
        request,
        form,
        formsets,
        change,
    ):
        super().save_related(
            request,
            form,
            formsets,
            change,
        )

        event = form.instance

        (
            activated_invitations,
            _,
        ) = sync_event_invitations(
            event,
            actor=request.user,
            request=request,
            source=AuditLog.Source.ADMIN,
            method=AuditLog.Method.MANUAL,
            send_notifications=(
                event.status
                == Event.Status.ACTIVE
            ),
        )

        old_value = getattr(
            event,
            "_admin_old_audit_value",
            None,
        )

        new_value = getattr(
            event,
            "_admin_new_audit_value",
            None,
        )

        was_change = getattr(
            event,
            "_admin_was_change",
            False,
        )

        if (
            not was_change
            or old_value is None
            or new_value is None
        ):
            return

        was_cancelled = (
            old_value.get("status")
            != Event.Status.CANCELLED
            and event.status
            == Event.Status.CANCELLED
        )

        if was_cancelled:
            notify_event_cancelled(
                event
            )

            return

        changed_fields = (
            material_event_changes(
                old_value,
                new_value,
            )
        )

        if not changed_fields:
            return

        newly_invited_user_ids = {
            invitation.user_id
            for invitation
            in activated_invitations
        }

        notify_event_updated(
            event,
            changed_fields,
            exclude_user_ids=(
                newly_invited_user_ids
            ),
        )


@admin.register(EventParticipation)
class EventParticipationAdmin(
    AuditedEventAdmin
):
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


@admin.register(EventInvitation)
class EventInvitationAdmin(
    admin.ModelAdmin
):
    list_display = (
        "user",
        "event",
        "is_active",
        "invited_at",
        "uninvited_at",
    )

    list_filter = (
        "is_active",
        "event",
    )

    search_fields = (
        "user__username",
        "user__display_name",
        "event__title",
    )

    readonly_fields = (
        "event",
        "user",
        "is_active",
        "invited_at",
        "uninvited_at",
    )

    def has_add_permission(
        self,
        request,
    ):
        return False

    def has_change_permission(
        self,
        request,
        obj=None,
    ):
        return False

    def has_delete_permission(
        self,
        request,
        obj=None,
    ):
        return False