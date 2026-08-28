from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .forms import LoginForm, RegistrationForm


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
        return redirect("tavern")

    if request.method == "POST":
        if request.POST.get("action") == "skip":
            request.user.push_prompt_seen = True

            request.user.save(
                update_fields=[
                    "push_prompt_seen",
                ],
            )

            return redirect("tavern")

    return render(
        request,
        "notifications/push_setup.html",
    )


def user_login(request):
    if request.user.is_authenticated:
        return redirect("tavern")

    if request.method == "POST":
        form = LoginForm(
            request=request,
            data=request.POST,
        )

        if form.is_valid():
            login(request, form.get_user())

            return redirect("tavern")
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

    return redirect("login")