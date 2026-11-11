
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.db import transaction

from audit.models import AuditLog
from audit.services import record_audit_event

from .models import (
    AccountStatus,
    User,
)


ACCOUNT_STATUS_TRANSITIONS = {
    AccountStatus.PENDING: {
        AccountStatus.MEMBER,
        AccountStatus.REJECTED,
        AccountStatus.DISABLED,
    },
    AccountStatus.MEMBER: {
        AccountStatus.SUSPENDED,
        AccountStatus.DISABLED,
    },
    AccountStatus.REJECTED: {
        AccountStatus.PENDING,
    },
    AccountStatus.SUSPENDED: {
        AccountStatus.MEMBER,
        AccountStatus.DISABLED,
    },
    AccountStatus.DISABLED: {
        AccountStatus.PENDING,
    },
}


def is_full_administrator(user):
    return (
        user.is_authenticated
        and user.is_active
        and user.is_staff
        and user.is_superuser
    )


def require_full_administrator(user):
    if not is_full_administrator(user):
        raise PermissionDenied


def require_account_manager(user):
    if not (
        user.is_authenticated
        and user.is_active
        and (
            user.has_perm("accounts.approve_membership")
            or user.has_perm("accounts.change_user")
        )
    ):
        raise PermissionDenied


def validate_account_target(
    *,
    actor,
    account,
):
    if actor.pk == account.pk:
        raise PermissionDenied(
            "You cannot modify your own account here."
        )

    if account.is_superuser:
        raise PermissionDenied(
            "Superuser accounts must be managed "
            "through Django administration."
        )


def get_allowed_account_statuses(
    *,
    actor,
    account,
):
    if not (
        actor.is_authenticated
        and actor.is_active
    ):
        return set()

    if (
        actor.pk == account.pk
        or account.is_superuser
    ):
        return set()

    full_administrator = is_full_administrator(
        actor
    )

    if (
        account.is_staff
        and not full_administrator
    ):
        return set()

    current_status = account.account_status

    possible_statuses = (
        ACCOUNT_STATUS_TRANSITIONS.get(
            current_status,
            set(),
        )
    )

    can_change_users = actor.has_perm(
        "accounts.change_user"
    )

    can_approve = actor.has_perm(
        "accounts.approve_membership"
    )

    allowed_statuses = set()

    for status in possible_statuses:
        is_approval_action = (
            current_status == AccountStatus.PENDING
            and status in {
                AccountStatus.MEMBER,
                AccountStatus.REJECTED,
            }
        )

        if is_approval_action:
            if can_approve or can_change_users:
                allowed_statuses.add(status)

        elif can_change_users:
            allowed_statuses.add(status)

    return allowed_statuses


def get_status_audit_action(
    *,
    old_status,
    new_status,
):
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


@transaction.atomic
def change_account_status(
    *,
    account,
    status,
    request,
):
    actor = request.user

    require_account_manager(actor)

    account = User.objects.select_for_update().get(
        pk=account.pk,
    )

    validate_account_target(
        actor=actor,
        account=account,
    )

    if status == account.account_status:
        return account

    allowed_statuses = get_allowed_account_statuses(
        actor=actor,
        account=account,
    )

    if status not in allowed_statuses:
        raise PermissionDenied(
            "This membership status transition "
            "is not permitted."
        )

    old_status = account.account_status

    account.account_status = status

    account.save(
        update_fields=[
            "account_status",
        ]
    )

    record_audit_event(
        actor=actor,
        request=request,
        action=get_status_audit_action(
            old_status=old_status,
            new_status=status,
        ),
        target_type="user account",
        target_id=account.pk,
        target_label=str(account),
        old_value={
            "account_status": old_status,
        },
        new_value={
            "account_status": status,
        },
        source=AuditLog.Source.WEB_APP,
        method=AuditLog.Method.MANUAL,
    )

    return account


@transaction.atomic
def set_account_active(
    *,
    account,
    is_active,
    request,
):
    actor = request.user

    require_full_administrator(actor)

    account = User.objects.select_for_update().get(
        pk=account.pk,
    )

    validate_account_target(
        actor=actor,
        account=account,
    )

    old_is_active = account.is_active
    new_is_active = bool(is_active)

    if old_is_active == new_is_active:
        return account

    account.is_active = new_is_active

    account.save(
        update_fields=[
            "is_active",
        ]
    )

    record_audit_event(
        actor=actor,
        request=request,
        action=AuditLog.Action.UPDATE,
        target_type="user account",
        target_id=account.pk,
        target_label=str(account),
        old_value={
            "is_active": old_is_active,
        },
        new_value={
            "is_active": new_is_active,
        },
        source=AuditLog.Source.WEB_APP,
        method=AuditLog.Method.MANUAL,
    )

    return account


@transaction.atomic
def set_account_groups(
    *,
    account,
    groups,
    request,
):
    actor = request.user

    require_full_administrator(actor)

    account = User.objects.select_for_update().get(
        pk=account.pk,
    )

    validate_account_target(
        actor=actor,
        account=account,
    )

    requested_group_ids = {
        group.pk
        for group in groups
    }

    valid_group_ids = set(
        Group.objects.filter(
            pk__in=requested_group_ids,
        ).values_list(
            "pk",
            flat=True,
        )
    )

    if valid_group_ids != requested_group_ids:
        raise PermissionDenied(
            "One or more selected roles are invalid."
        )

    old_groups = set(
        account.groups.values_list(
            "name",
            flat=True,
        )
    )

    account.groups.set(
        valid_group_ids,
    )

    new_groups = set(
        account.groups.values_list(
            "name",
            flat=True,
        )
    )

    added_groups = sorted(
        new_groups - old_groups
    )

    removed_groups = sorted(
        old_groups - new_groups
    )

    for group_name in added_groups:
        record_audit_event(
            actor=actor,
            request=request,
            action=AuditLog.Action.ASSIGN,
            target_type="application role",
            target_id=account.pk,
            target_label=str(account),
            new_value={
                "role": group_name,
            },
            source=AuditLog.Source.WEB_APP,
            method=AuditLog.Method.MANUAL,
        )

    for group_name in removed_groups:
        record_audit_event(
            actor=actor,
            request=request,
            action=AuditLog.Action.REMOVE,
            target_type="application role",
            target_id=account.pk,
            target_label=str(account),
            old_value={
                "role": group_name,
            },
            source=AuditLog.Source.WEB_APP,
            method=AuditLog.Method.MANUAL,
        )

    return account
