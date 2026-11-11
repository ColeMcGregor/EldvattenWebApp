
from django.contrib import messages
from django.contrib.auth import (
    login,
    logout,
    update_session_auth_hash,
)
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import (
    require_GET,
    require_POST,
)

from .directory import (
    allowed_directory_groups,
    can_access_directory,
    filter_directory_members,
    visible_directory_members,
)
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
    get_profile_context,
)
from .services import register_account


def register(request):
    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":
        form = RegistrationForm(request.POST)

        if form.is_valid():
            user = register_account(
                form=form,
            )

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


@login_required
@require_GET
@never_cache
def directory_index(request):
    if not can_access_directory(request.user):
        return HttpResponseForbidden(
            "Only active members can access the Directory."
        )

    search = request.GET.get("q", "").strip()[:100]
    group = request.GET.get("group", "").strip()
    category = request.GET.get("category", "all").strip()
    selected_id = request.GET.get("member", "").strip()

    groups = allowed_directory_groups(request.user)
    allowed_categories = {
        section["key"]
        for section in groups
    }

    if (
        category != "all"
        and category not in allowed_categories
    ):
        raise Http404

    allowed_values = {
        choice["value"]
        for section in groups
        for choice in section["choices"]
    }

    if group and group not in allowed_values:
        raise Http404

    if (
        group
        and category not in (
            "all",
            group.split(":", 1)[0],
        )
    ):
        raise Http404

    members = filter_directory_members(
        visible_directory_members(request.user),
        search=search,
        group=group,
    )

    if category != "all" and not group:
        members = members.none()

    selected_member = None

    if selected_id:
        if (
            not selected_id.isdecimal()
            or len(selected_id) > 20
        ):
            raise Http404

        selected_member = get_object_or_404(
            members,
            pk=int(selected_id),
        )

    context = {
        "directory_members": members,
        "directory_groups": groups,
        "search_query": search,
        "selected_group": group,
        "selected_category": category,
        "selected_member": selected_member,
        "profile_heading": "Member Profile",
    }

    if selected_member is not None:
        context.update(
            get_profile_context(selected_member)
        )

    if (
        request.headers.get("X-Requested-With")
        == "XMLHttpRequest"
    ):
        return render(
            request,
            "accounts/directory/profile_panel.html",
            context,
        )

    return render(
        request,
        "accounts/directory/index.html",
        context,
    )
