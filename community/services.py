from django.db.models import Prefetch, Q

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

from .models import Post, PostTarget


TAVERN_ACCOUNT_STATUSES = {
    AccountStatus.PENDING,
    AccountStatus.MEMBER,
}


def resolve_post_target(target):
    user_ids = set(
        User.objects.filter(
            account_status__in=TAVERN_ACCOUNT_STATUSES,
            is_active=True,
        ).values_list(
            "id",
            flat=True,
        )
    )

    if target.user is not None:
        if (
            target.user.is_active
            and target.user.account_status
            in TAVERN_ACCOUNT_STATUSES
        ):
            return {
                target.user.id,
            }

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


def resolve_post_targets(post):
    resolved_user_ids = set()

    for target in post.targets.all():
        resolved_user_ids.update(
            resolve_post_target(target)
        )

    return resolved_user_ids


def user_can_view_post(user, post):
    if not user.is_authenticated:
        return False

    if not user.is_active:
        return False

    if user.account_status not in TAVERN_ACCOUNT_STATUSES:
        return False

    if post.is_deleted:
        return False

    if post.author_id == user.id:
        return True

    if post.visibility == Post.Visibility.ALL:
        return True

    if (
        post.visibility == Post.Visibility.GUESTS
        and user.account_status
        == AccountStatus.PENDING
    ):
        return True

    if (
        post.visibility == Post.Visibility.MEMBERS
        and user.account_status
        == AccountStatus.MEMBER
    ):
        return True

    if (
        post.visibility
        == Post.Visibility.SELECTED_GROUPS
    ):
        return user.id in resolve_post_targets(post)

    return False


def get_visible_posts(user):
    if not user.is_authenticated:
        return Post.objects.none()

    if not user.is_active:
        return Post.objects.none()

    if user.account_status not in TAVERN_ACCOUNT_STATUSES:
        return Post.objects.none()

    selected_target_queryset = (
        PostTarget.objects
        .select_related(
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
    )

    selected_posts = (
        Post.objects
        .filter(
            visibility=Post.Visibility.SELECTED_GROUPS,
            is_deleted=False,
        )
        .prefetch_related(
            Prefetch(
                "targets",
                queryset=selected_target_queryset,
            )
        )
    )

    selected_post_ids = set()

    for post in selected_posts:
        if user.id in resolve_post_targets(post):
            selected_post_ids.add(post.id)

    visibility_query = Q(
        author=user,
    ) | Q(
        visibility=Post.Visibility.ALL,
    )

    if user.account_status == AccountStatus.PENDING:
        visibility_query |= Q(
            visibility=Post.Visibility.GUESTS,
        )

    if user.account_status == AccountStatus.MEMBER:
        visibility_query |= Q(
            visibility=Post.Visibility.MEMBERS,
        )

    if selected_post_ids:
        visibility_query |= Q(
            id__in=selected_post_ids,
        )

    return (
        Post.objects
        .filter(
            visibility_query,
            is_deleted=False,
        )
        .select_related("author")
        .distinct()
        .order_by("-created_at")
    )