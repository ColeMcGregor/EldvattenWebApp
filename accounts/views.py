from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.db.models import F, Q
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from actions.models import ActionAssignment
from voting.models import Vote, VoteEligibleUser

from .forms import LoginForm, RegistrationForm


MY_ELDVATTEN_SECTIONS = (
    "profile",
    "todo",
    "notifications",
    "settings",
)


def is_mobile_request(request):
    user_agent = request.META.get(
        "HTTP_USER_AGENT",
        "",
    ).lower()

    return any(
        mobile_term in user_agent
        for mobile_term in [
            "android",
            "iphone",
            "ipod",
            "mobile",
        ]
    )


def get_profile_context(user):
    citizenship_record = (
        user.citizenship_records
        .filter(
            ended_at__isnull=True,
        )
        .select_related(
            "citizenship_class",
            "chapter",
        )
        .first()
    )

    social_rank_record = (
        user.social_rank_records
        .filter(
            ended_at__isnull=True,
        )
        .select_related(
            "social_rank",
        )
        .first()
    )

    household_memberships = list(
        user.household_memberships
        .filter(
            ended_at__isnull=True,
        )
        .select_related(
            "household",
        )
        .order_by(
            "household__name",
        )
    )

    office_records = list(
        user.office_records
        .filter(
            ended_at__isnull=True,
        )
        .select_related(
            "office",
            "chapter",
        )
        .order_by(
            "office__name",
            "chapter__name",
        )
    )

    governance_memberships = list(
        user.governance_memberships
        .filter(
            ended_at__isnull=True,
        )
        .select_related(
            "governance_body",
        )
        .order_by(
            "governance_body__name",
        )
    )

    order_memberships = list(
        user.order_memberships
        .filter(
            ended_at__isnull=True,
        )
        .select_related(
            "order",
            "order_rank",
        )
        .order_by(
            "order__name",
        )
    )

    household_leadership_records = list(
        user.household_leadership_records
        .filter(
            ended_at__isnull=True,
        )
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
        .filter(
            ended_at__isnull=True,
        )
        .select_related(
            "community_group",
        )
        .order_by(
            "community_group__name",
        )
    )

    return {
        "profile_citizenship": citizenship_record,
        "profile_social_rank": social_rank_record,
        "profile_households": household_memberships,
        "profile_offices": office_records,
        "profile_governance_bodies": governance_memberships,
        "profile_orders": order_memberships,
        "profile_household_leadership": (
            household_leadership_records
        ),
        "profile_community_groups": (
            community_group_memberships
        ),
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
        .select_related(
            "action",
        )
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
            Q(
                vote__opens_at__isnull=True,
            )
            | Q(
                vote__opens_at__lte=now,
            )
        )
        .filter(
            Q(
                vote__closes_at__isnull=True,
            )
            | Q(
                vote__closes_at__gt=now,
            )
        )
        .select_related(
            "vote",
        )
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


def register(request):
    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":
        form = RegistrationForm(request.POST)

        if form.is_valid():
            user = form.save()
            login(request, user)

            return redirect("notification_setup")
    else:
        form = RegistrationForm()

    return render(
        request,
        "accounts/register.html",
        {"form": form},
    )


@login_required
def notification_setup(request):
    if request.user.push_prompt_seen:
        return redirect("tavern_main")

    if request.method == "POST":
        if request.POST.get("action") == "skip":
            request.user.push_prompt_seen = True

            request.user.save(
                update_fields=[
                    "push_prompt_seen",
                ],
            )

            return redirect("tavern_main")

    return render(
        request,
        "notifications/push_setup.html",
    )


@login_required
def my_eldvatten(request):
    active_section = request.GET.get(
        "section",
        "profile",
    )

    if active_section not in MY_ELDVATTEN_SECTIONS:
        active_section = "profile"

    context = {
        "active_section": active_section,
    }

    if active_section == "profile":
        context.update(
            get_profile_context(
                request.user,
            )
        )

    elif active_section == "todo":
        context.update(
            get_todo_context(
                request.user,
            )
        )

    if is_mobile_request(request):
        template_name = (
            "accounts/my_eldvatten_mobile.html"
        )
    else:
        template_name = (
            "accounts/my_eldvatten_desktop.html"
        )

    return render(
        request,
        template_name,
        context,
    )


def user_login(request):
    if request.user.is_authenticated:
        return redirect("tavern_main")

    if request.method == "POST":
        form = LoginForm(
            request=request,
            data=request.POST,
        )

        if form.is_valid():
            login(request, form.get_user())

            return redirect(
                "notifications:push_login_sync"
            )
    else:
        form = LoginForm(request=request)

    return render(
        request,
        "accounts/login.html",
        {"form": form},
    )


@require_POST
def user_logout(request):
    logout(request)

    return redirect("home")