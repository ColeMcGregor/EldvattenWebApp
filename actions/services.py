from django.utils import timezone

from accounts.models import AccountStatus, User
from audit.services import record_audit_event
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

from .models import ActionAssignment


def resolve_action_target(target):
    user_ids = set(
        User.objects.filter(
            account_status=AccountStatus.MEMBER,
            is_active=True,
        ).values_list(
            "id",
            flat=True,
        )
    )

    if target.user is not None:
        if (
            target.user.is_active
            and target.user.account_status == AccountStatus.MEMBER
        ):
            return {target.user.id}

        return set()

    if target.citizenship_class is not None:
        matching_ids = set(
            CitizenshipRecord.objects.filter(
                citizenship_class=target.citizenship_class,
                ended_at__isnull=True,
            ).values_list(
                "user_id",
                flat=True,
            )
        )

        user_ids &= matching_ids

    if target.social_rank is not None:
        matching_ids = set(
            UserSocialRank.objects.filter(
                social_rank=target.social_rank,
                ended_at__isnull=True,
            ).values_list(
                "user_id",
                flat=True,
            )
        )

        user_ids &= matching_ids

    if target.office is not None:
        office_records = UserOffice.objects.filter(
            office=target.office,
            ended_at__isnull=True,
        )

        if target.chapter is not None:
            office_records = office_records.filter(
                chapter=target.chapter,
            )

        matching_ids = set(
            office_records.values_list(
                "user_id",
                flat=True,
            )
        )

        user_ids &= matching_ids

    if target.chapter is not None:
        matching_ids = set(
            CitizenshipRecord.objects.filter(
                chapter=target.chapter,
                ended_at__isnull=True,
            ).values_list(
                "user_id",
                flat=True,
            )
        )

        user_ids &= matching_ids

    if target.household is not None:
        matching_ids = set(
            HouseholdMembership.objects.filter(
                household=target.household,
                ended_at__isnull=True,
            ).values_list(
                "user_id",
                flat=True,
            )
        )

        user_ids &= matching_ids

    if target.governance_body is not None:
        matching_ids = set(
            GovernanceMembership.objects.filter(
                governance_body=target.governance_body,
                ended_at__isnull=True,
            ).values_list(
                "user_id",
                flat=True,
            )
        )

        user_ids &= matching_ids

    if target.order is not None:
        order_records = OrderMembership.objects.filter(
            order=target.order,
            ended_at__isnull=True,
        )

        if target.order_rank is not None:
            order_records = order_records.filter(
                order_rank=target.order_rank,
            )

        matching_ids = set(
            order_records.values_list(
                "user_id",
                flat=True,
            )
        )

        user_ids &= matching_ids

    elif target.order_rank is not None:
        matching_ids = set(
            OrderMembership.objects.filter(
                order_rank=target.order_rank,
                ended_at__isnull=True,
            ).values_list(
                "user_id",
                flat=True,
            )
        )

        user_ids &= matching_ids

    if target.community_group is not None:
        matching_ids = set(
            GroupMembership.objects.filter(
                community_group=target.community_group,
                ended_at__isnull=True,
            ).values_list(
                "user_id",
                flat=True,
            )
        )

        user_ids &= matching_ids

    if target.household_leadership_type is not None:
        leadership_records = HouseholdLeadership.objects.filter(
            leadership_type=target.household_leadership_type,
            ended_at__isnull=True,
        )

        if target.household is not None:
            leadership_records = leadership_records.filter(
                household=target.household,
            )

        matching_ids = set(
            leadership_records.values_list(
                "user_id",
                flat=True,
            )
        )

        user_ids &= matching_ids

    return user_ids


def resolve_action_targets(action):
    resolved_user_ids = set()

    for target in action.targets.all():
        resolved_user_ids.update(
            resolve_action_target(target)
        )

    return resolved_user_ids


def assignment_audit_values(assignment):
    return {
        "action_id": assignment.action_id,
        "action": assignment.action.title,
        "user_id": assignment.user_id,
        "user": (
            assignment.user.display_name
            or assignment.user.get_username()
        ),
        "status": assignment.status,
        "is_active": assignment.is_active,
        "assigned_at": (
            assignment.assigned_at.isoformat()
            if assignment.assigned_at
            else None
        ),
        "unassigned_at": (
            assignment.unassigned_at.isoformat()
            if assignment.unassigned_at
            else None
        ),
        "opened_at": (
            assignment.opened_at.isoformat()
            if assignment.opened_at
            else None
        ),
        "completed_at": (
            assignment.completed_at.isoformat()
            if assignment.completed_at
            else None
        ),
    }


def sync_action_assignments(
    action,
    *,
    actor=None,
    request=None,
    source="SYSTEM",
    method="AUTOMATIC",
):
    resolved_user_ids = resolve_action_targets(action)

    existing_assignments = {
        assignment.user_id: assignment
        for assignment in ActionAssignment.objects.filter(
            action=action,
        ).select_related(
            "user",
            "action",
        )
    }

    activated_assignments = []
    deactivated_assignments = []

    now = timezone.now()

    for user_id in resolved_user_ids:
        assignment = existing_assignments.get(user_id)

        if assignment is None:
            assignment = ActionAssignment.objects.create(
                action=action,
                user_id=user_id,
            )

            assignment = ActionAssignment.objects.select_related(
                "user",
                "action",
            ).get(
                id=assignment.id,
            )

            record_audit_event(
                action="ASSIGN",
                target_type="ActionAssignment",
                target_id=assignment.id,
                target_label=str(assignment),
                actor=actor,
                request=request,
                old_value=None,
                new_value=assignment_audit_values(assignment),
                effective_at=assignment.assigned_at,
                source=source,
                method=method,
                notes="Action assignment created from current action targets.",
            )

            activated_assignments.append(assignment)
            continue

        if not assignment.is_active:
            old_value = assignment_audit_values(assignment)

            assignment.is_active = True
            assignment.unassigned_at = None

            assignment.full_clean()
            assignment.save(
                update_fields=[
                    "is_active",
                    "unassigned_at",
                ]
            )

            record_audit_event(
                action="ASSIGN",
                target_type="ActionAssignment",
                target_id=assignment.id,
                target_label=str(assignment),
                actor=actor,
                request=request,
                old_value=old_value,
                new_value=assignment_audit_values(assignment),
                effective_at=now,
                source=source,
                method=method,
                notes="Action assignment reactivated from current action targets.",
            )

            activated_assignments.append(assignment)

    for user_id, assignment in existing_assignments.items():
        if user_id in resolved_user_ids:
            continue

        if not assignment.is_active:
            continue

        old_value = assignment_audit_values(assignment)

        assignment.is_active = False
        assignment.unassigned_at = now

        assignment.full_clean()
        assignment.save(
            update_fields=[
                "is_active",
                "unassigned_at",
            ]
        )

        record_audit_event(
            action="REMOVE",
            target_type="ActionAssignment",
            target_id=assignment.id,
            target_label=str(assignment),
            actor=actor,
            request=request,
            old_value=old_value,
            new_value=assignment_audit_values(assignment),
            effective_at=assignment.unassigned_at,
            source=source,
            method=method,
            notes="Action assignment deactivated because the user no longer matches the current action targets.",
        )

        deactivated_assignments.append(assignment)

    return activated_assignments, deactivated_assignments