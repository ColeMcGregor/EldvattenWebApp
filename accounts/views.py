from django.contrib.auth import login, logout
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

            return redirect("tavern")
    else:
        form = RegistrationForm()

    return render(
        request,
        "accounts/register.html",
        {"form": form},
    )


def user_login(request):
    if request.user.is_authenticated:
        return redirect("messaging:conversation_list")

    if request.method == "POST":
        form = LoginForm(
            request=request,
            data=request.POST,
        )

        if form.is_valid():
            login(request, form.get_user())

            return redirect("messaging:conversation_list")
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