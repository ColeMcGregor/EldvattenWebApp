from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

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