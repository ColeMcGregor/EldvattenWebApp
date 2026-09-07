from django.db.models import F, Q
from django.utils import timezone

from actions.models import ActionAssignment
from community.models import Post
from notifications.forms import NotificationPreferenceForm
from notifications.models import (
    Notification,
    NotificationPreference,
)
from notifications.services import (
    get_unread_notification_count,
    get_user_notifications,
)
from voting.models import Vote, VoteEligibleUser

from .forms import (
    AccountSettingsForm,
    UserPasswordChangeForm,
)


MY_ELDVATTEN_SECTIONS = (
    "profile",
    "posts",
    "todo",
    "notifications",
    "settings",
)


def get_active_section(request):
    active_section = request.GET.get(
        "section",
        "profile",
    )

    if active_section not in MY_ELDVATTEN_SECTIONS:
        return "profile"

    return active_section


def get_my_eldvatten_template(request):
    user_agent = request.META.get(
        "HTTP_USER_AGENT",
        "",
    ).lower()

    is_mobile = any(
        mobile_term in user_agent
        for mobile_term in [
            "android",
            "iphone",
            "ipod",
            "mobile",
        ]
    )

    if is_mobile:
        return "accounts/my_eldvatten_mobile.html"

    return "accounts/my_eldvatten_desktop.html"


def get_profile_context(user):
    citizenship_record = (
        user.citizenship_records
        .filter(ended_at__isnull=True)
        .select_related("citizenship_class", "chapter")
        .first()
    )

    social_rank_record = (
        user.social_rank_records
        .filter(ended_at__isnull=True)
        .select_related("social_rank")
        .first()
    )

    household_memberships = list(
        user.household_memberships
        .filter(ended_at__isnull=True)
        .select_related("household")
        .order_by("household__name")
    )

    office_records = list(
        user.office_records
        .filter(ended_at__isnull=True)
        .select_related("office", "chapter")
        .order_by("office__name", "chapter__name")
    )

    governance_memberships = list(
        user.governance_memberships
        .filter(ended_at__isnull=True)
        .select_related("governance_body")
        .order_by("governance_body__name")
    )

    order_memberships = list(
        user.order_memberships
        .filter(ended_at__isnull=True)
        .select_related("order", "order_rank")
        .order_by("order__name")
    )

    household_leadership_records = list(
        user.household_leadership_records
        .filter(ended_at__isnull=True)
        .select_related(
            "household",
            "leadership_type",
        )
        .order_by(
            "household__name",
            "leadership_type__name",
        )
    )

    community_group_memberships = list(
        user.community_group_memberships
        .filter(ended_at__isnull=True)
        .select_related("community_group")
        .order_by("community_group__name")
    )

    return {
        "profile_citizenship": citizenship_record,
        "profile_social_rank": social_rank_record,
        "profile_households": household_memberships,
        "profile_offices": office_records,
        "profile_governance_bodies":
            governance_memberships,
        "profile_orders": order_memberships,
        "profile_household_leadership":
            household_leadership_records,
        "profile_community_groups":
            community_group_memberships,
    }


def get_posts_context(user):
    posts = list(
        Post.objects
        .filter(
            author=user,
        )
        .select_related("author")
        .order_by("-created_at")
    )

    return {
        "my_posts": posts,
    }


def get_todo_context(user):
    now = timezone.now()

    action_assignments = list(
        ActionAssignment.objects
        .filter(
            user=user,
            is_active=True,
        )
        .exclude(
            status=ActionAssignment.Status.COMPLETED,
        )
        .select_related("action")
        .order_by(
            F("action__deadline").asc(
                nulls_last=True,
            ),
            "-assigned_at",
        )
    )

    vote_eligibilities = list(
        VoteEligibleUser.objects
        .filter(
            user=user,
            has_responded=False,
            vote__status=Vote.Status.OPEN,
        )
        .filter(
            Q(vote__opens_at__isnull=True)
            | Q(vote__opens_at__lte=now)
        )
        .filter(
            Q(vote__closes_at__isnull=True)
            | Q(vote__closes_at__gt=now)
        )
        .select_related("vote")
        .order_by(
            F("vote__closes_at").asc(
                nulls_last=True,
            ),
            "-vote__opened_at",
        )
    )

    return {
        "todo_actions": action_assignments,
        "todo_votes": vote_eligibilities,
    }


def get_notification_context(
    user,
    query_parameters,
):
    read_state = query_parameters.get(
        "state",
        "all",
    )

    if read_state not in {
        "all",
        "unread",
        "read",
    }:
        read_state = "all"

    notification_type = query_parameters.get(
        "type",
        "all",
    )

    if (
        notification_type != "all"
        and notification_type
        not in Notification.Type.values
    ):
        notification_type = "all"

    notifications = list(
        get_user_notifications(
            user,
            read_state=read_state,
            notification_type=notification_type,
        )
    )

    return {
        "notifications": notifications,
        "unread_count":
            get_unread_notification_count(user),
        "notification_state_filter":
            read_state,
        "notification_type_filter":
            notification_type,
        "notification_type_choices":
            Notification.Type.choices,
    }


def get_settings_context(
    user,
    query_parameters,
):
    notification_preference = (
        NotificationPreference.objects
        .filter(
            user=user,
        )
        .first()
    )

    if notification_preference is None:
        notification_preference = (
            NotificationPreference(
                user=user,
            )
        )

    return {
        "account_settings_form":
            AccountSettingsForm(
                instance=user,
            ),
        "password_change_form":
            UserPasswordChangeForm(
                user=user,
            ),
        "notification_preference_form":
            NotificationPreferenceForm(
                instance=notification_preference,
            ),
        "password_modal_open":
            query_parameters.get("password")
            == "open",
    }


def build_my_eldvatten_context(
    *,
    user,
    active_section,
    query_parameters,
):
    context = {
        "active_section": active_section,
    }

    if active_section == "profile":
        context.update(
            get_profile_context(user)
        )

    elif active_section == "posts":
        context.update(
            get_posts_context(user)
        )

    elif active_section == "todo":
        context.update(
            get_todo_context(user)
        )

    elif active_section == "notifications":
        context.update(
            get_notification_context(
                user,
                query_parameters,
            )
        )

    elif active_section == "settings":
        context.update(
            get_settings_context(
                user,
                query_parameters,
            )
        )

    return context