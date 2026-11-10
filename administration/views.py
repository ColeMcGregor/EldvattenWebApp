
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import render

from .permissions import can_access_administration
from .sections import (
    get_administration_sections,
    get_section_links,
)


@login_required
def administration_index(request):
    if not can_access_administration(request.user):
        raise PermissionDenied

    sections = get_administration_sections(request.user)

    return render(
        request,
        "administration/index.html",
        {
            "sections": sections,
        },
    )


@login_required
def administration_section(request, section_slug):
    if not can_access_administration(request.user):
        raise PermissionDenied

    sections = get_administration_sections(request.user)

    section = next(
        (
            item
            for item in sections
            if item["slug"] == section_slug
        ),
        None,
    )

    if section is None:
        raise Http404("Administration section not found.")

    if not section["allowed"]:
        raise PermissionDenied

    links = get_section_links(
        request.user,
        section_slug,
    )

    return render(
        request,
        "administration/section.html",
        {
            "section": section,
            "links": links,
        },
    )
