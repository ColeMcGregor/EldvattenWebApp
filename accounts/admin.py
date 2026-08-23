from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from audit.models import AuditLog
from audit.services import record_audit_event

from .models import AccountStatus, User


class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        (
            "EldVatten Account",
            {
                "fields": (
                    "display_name",
                    "account_status",
                )
            },
        ),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        (
            "EldVatten Account",
            {
                "fields": (
                    "display_name",
                    "account_status",
                )
            },
        ),
    )

    list_display = (
        "username",
        "email",
        "display_name",
        "account_status",
        "is_staff",
        "is_active",
    )

    def get_audit_values(self, user):
        return {
            "username": user.username,
            "email": user.email,
            "display_name": user.display_name,
            "account_status": user.get_account_status_display(),
            "is_staff": user.is_staff,
            "is_active": user.is_active,
        }

    def get_account_status_action(self, old_status, new_status):
        if (
            old_status == AccountStatus.PENDING
            and new_status == AccountStatus.MEMBER
        ):
            return AuditLog.Action.APPROVE

        if new_status == AccountStatus.SUSPENDED:
            return AuditLog.Action.SUSPEND

        if (
            old_status == AccountStatus.SUSPENDED
            and new_status == AccountStatus.MEMBER
        ):
            return AuditLog.Action.RESTORE

        return AuditLog.Action.UPDATE

    def save_model(self, request, obj, form, change):
        old_value = None
        old_status = None

        if change:
            old_user = User.objects.get(pk=obj.pk)
            old_value = self.get_audit_values(old_user)
            old_status = old_user.account_status

        super().save_model(request, obj, form, change)

        if change:
            action = self.get_account_status_action(
                old_status,
                obj.account_status,
            )
        else:
            action = AuditLog.Action.CREATE

        record_audit_event(
            actor=request.user,
            request=request,
            action=action,
            target_type="user account",
            target_id=obj.pk,
            target_label=str(obj),
            old_value=old_value,
            new_value=self.get_audit_values(obj),
            source=AuditLog.Source.ADMIN,
            method=AuditLog.Method.MANUAL,
        )

    def save_related(self, request, form, formsets, change):
        user = form.instance

        old_groups = set(
            user.groups.values_list("name", flat=True)
        )

        super().save_related(
            request,
            form,
            formsets,
            change,
        )

        new_groups = set(
            user.groups.values_list("name", flat=True)
        )

        added_groups = sorted(new_groups - old_groups)
        removed_groups = sorted(old_groups - new_groups)

        for group_name in added_groups:
            record_audit_event(
                actor=request.user,
                request=request,
                action=AuditLog.Action.ASSIGN,
                target_type="application role",
                target_id=user.pk,
                target_label=str(user),
                old_value=None,
                new_value={
                    "role": group_name,
                },
                source=AuditLog.Source.ADMIN,
                method=AuditLog.Method.MANUAL,
            )

        for group_name in removed_groups:
            record_audit_event(
                actor=request.user,
                request=request,
                action=AuditLog.Action.REMOVE,
                target_type="application role",
                target_id=user.pk,
                target_label=str(user),
                old_value={
                    "role": group_name,
                },
                new_value=None,
                source=AuditLog.Source.ADMIN,
                method=AuditLog.Method.MANUAL,
            )


admin.site.register(User, CustomUserAdmin)