from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect

from .models import Resource
from .services import can_view_resource


@login_required
def download_resource(
    request,
    resource_id,
):
    resource = get_object_or_404(
        Resource,
        id=resource_id,
    )

    if not can_view_resource(
        request.user,
        resource,
    ):
        raise Http404

    if (
        resource.resource_type
        != Resource.ResourceType.FILE
    ):
        raise Http404

    if not resource.file:
        raise Http404

    try:
        file_handle = resource.file.open(
            "rb"
        )
    except FileNotFoundError:
        raise Http404

    return FileResponse(
        file_handle,
        as_attachment=True,
        filename=resource.filename,
    )


@login_required
def open_resource(
    request,
    resource_id,
):
    resource = get_object_or_404(
        Resource,
        id=resource_id,
    )

    if not can_view_resource(
        request.user,
        resource,
    ):
        raise Http404

    if (
        resource.resource_type
        != Resource.ResourceType.LINK
    ):
        raise Http404

    if not resource.external_url:
        raise Http404

    return redirect(
        resource.external_url
    )