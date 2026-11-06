from django.db.models import Q

from messaging.models import UserBlock
from organization.models import (
    Chapter,
    CommunityGroup,
    GovernanceBody,
    Household,
    Order,
)

from .models import AccountStatus, User


DIRECTORY_GROUPS = (
    (
        "chapter",
        "Chapters",
        Chapter,
        "citizenship_records",
        "citizenship_records",
        "chapter_id",
    ),
    (
        "household",
        "Households",
        Household,
        "memberships",
        "household_memberships",
        "household_id",
    ),
    (
        "group",
        "Groups",
        CommunityGroup,
        "memberships",
        "community_group_memberships",
        "community_group_id",
    ),
    (
        "order",
        "Orders",
        Order,
        "memberships",
        "order_memberships",
        "order_id",
    ),
    (
        "governance",
        "Governance Bodies",
        GovernanceBody,
        "memberships",
        "governance_memberships",
        "governance_body_id",
    ),
)


def can_access_directory(user):
    return (
        user.is_authenticated
        and user.is_active
        and user.account_status == AccountStatus.MEMBER
    )


def visible_directory_members(user):
    if not can_access_directory(user):
        return User.objects.none()

    blocked_by_viewer = UserBlock.objects.filter(
        blocker=user,
    ).values_list("blocked_id", flat=True)
    blocking_viewer = UserBlock.objects.filter(
        blocked=user,
    ).values_list("blocker_id", flat=True)

    return (
        User.objects
        .filter(
            account_status=AccountStatus.MEMBER,
            is_active=True,
        )
        .exclude(pk__in=blocked_by_viewer)
        .exclude(pk__in=blocking_viewer)
        .order_by("display_name", "username", "pk")
    )


def allowed_directory_groups(user):
    if not can_access_directory(user):
        return []

    groups = []

    for key, title, model, _, _, _ in DIRECTORY_GROUPS:
        choices = [
            {
                "value": f"{key}:{record.pk}",
                "label": record.name,
            }
            for record in model.objects.order_by("name")
        ]

        groups.append({
            "key": key,
            "title": title,
            "choices": choices,
        })

    return groups


def filter_directory_members(members, *, search="", group=""):
    for word in search.split():
        members = members.filter(
            Q(display_name__icontains=word)
            | Q(username__icontains=word)
            | Q(first_name__icontains=word)
            | Q(last_name__icontains=word)
        )

    if group:
        group_type, group_id = group.split(":", 1)

        for key, _, _, _, member_relation, member_key in DIRECTORY_GROUPS:
            if key == group_type:
                members = members.filter(**{
                    f"{member_relation}__{member_key}": int(group_id),
                    f"{member_relation}__ended_at__isnull": True,
                }).distinct()
                break

    return members
