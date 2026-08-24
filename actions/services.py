from accounts.models import AccountStatus, User
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


def create_action_assignments(action):
    user_ids = resolve_action_targets(action)

    assignments = []

    for user_id in user_ids:
        assignment, created = ActionAssignment.objects.get_or_create(
            action=action,
            user_id=user_id,
        )

        if created:
            assignments.append(assignment)

    return assignments