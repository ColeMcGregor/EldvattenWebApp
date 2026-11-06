from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from .directory import (
    allowed_directory_groups,
    can_access_directory,
    filter_directory_members,
    visible_directory_members,
)
from .my_eldvatten import get_profile_context


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
    allowed_categories = {section["key"] for section in groups}

    if category != "all" and category not in allowed_categories:
        raise Http404

    allowed_values = {
        choice["value"]
        for section in groups
        for choice in section["choices"]
    }

    if group and group not in allowed_values:
        raise Http404

    if group and category not in ("all", group.split(":", 1)[0]):
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
        if not selected_id.isdecimal() or len(selected_id) > 20:
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
        context.update(get_profile_context(selected_member))

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
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
