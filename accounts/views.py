from django.contrib import messages
from django.contrib.auth import (
    login,
    logout,
    update_session_auth_hash,
)
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .forms import (
    AccountSettingsForm,
    LoginForm,
    RegistrationForm,
    UserPasswordChangeForm,
)
from .my_eldvatten import (
    build_my_eldvatten_context,
    get_active_section,
    get_my_eldvatten_template,
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
        {
            "form": form,
        },
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
    active_section = get_active_section(
        request,
    )

    context = build_my_eldvatten_context(
        user=request.user,
        active_section=active_section,
        query_parameters=request.GET,
    )

    template_name = get_my_eldvatten_template(
        request,
    )

    return render(
        request,
        template_name,
        context,
    )


@login_required
@require_POST
def my_eldvatten_account_update(request):
    form = AccountSettingsForm(
        request.POST,
        instance=request.user,
    )

    if form.is_valid():
        form.save()

        messages.success(
            request,
            "Account settings saved.",
        )
    else:
        for errors in form.errors.values():
            for error in errors:
                messages.error(
                    request,
                    error,
                )

    settings_url = (
        f"{reverse('my_eldvatten')}"
        "?section=settings"
    )

    return redirect(settings_url)


@login_required
@require_POST
def my_eldvatten_password_change(request):
    form = UserPasswordChangeForm(
        user=request.user,
        data=request.POST,
    )

    if form.is_valid():
        user = form.save()

        update_session_auth_hash(
            request,
            user,
        )

        messages.success(
            request,
            "Password changed.",
        )

        settings_url = (
            f"{reverse('my_eldvatten')}"
            "?section=settings"
        )

        return redirect(settings_url)

    for errors in form.errors.values():
        for error in errors:
            messages.error(
                request,
                error,
            )

    settings_url = (
        f"{reverse('my_eldvatten')}"
        "?section=settings"
        "&password=open"
    )

    return redirect(settings_url)


def user_login(request):
    if request.user.is_authenticated:
        return redirect("tavern_main")

    if request.method == "POST":
        form = LoginForm(
            request=request,
            data=request.POST,
        )

        if form.is_valid():
            login(
                request,
                form.get_user(),
            )

            return redirect(
                "notifications:push_login_sync",
            )
    else:
        form = LoginForm(
            request=request,
        )

    return render(
        request,
        "accounts/login.html",
        {
            "form": form,
        },
    )


@require_POST
def user_logout(request):
    logout(request)

    return redirect("home")