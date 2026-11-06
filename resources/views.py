
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from accounts.models import AccountStatus, User
from audit.models import AuditLog
from audit.services import record_audit_event

from .forms import ResourceForm, ResourceTargetFormSet
from .models import Resource
from .services import (
    can_view_resource,
    is_member,
    resolve_resource_exclude_targets,
    resolve_resource_include_targets,
    visible_resources_for_user,
)


TARGET_SELECTORS = (
    "user",
    "citizenship_class",
    "social_rank",
    "office",
    "chapter",
    "household",
    "governance_body",
    "order",
    "order_rank",
    "community_group",
    "household_leadership_type",
)


def resource_values(resource):
    targets = []

    for target in resource.targets.order_by("pk"):
        item = {
            "effect": target.effect,
        }

        for field in TARGET_SELECTORS:
            item[field] = getattr(
                target,
                f"{field}_id",
            )

        targets.append(item)

    return {
        "title": resource.title,
        "description": resource.description,
        "resource_type": resource.resource_type,
        "file": resource.file.name if resource.file else "",
        "external_url": resource.external_url,
        "visibility": resource.visibility,
        "sort_order": resource.sort_order,
        "is_active": resource.is_active,
        "targets": targets,
    }


def record_resource_change(
    request,
    resource,
    action,
    old_value,
):
    record_audit_event(
        action=action,
        target_type="Resource",
        target_id=resource.pk,
        target_label=resource.title,
        actor=request.user,
        request=request,
        old_value=old_value,
        new_value=resource_values(resource),
        source=AuditLog.Source.WEB_APP,
        method=AuditLog.Method.MANUAL,
    )


def resource_tabs_context(user):
    return {
        "can_manage_resources": user.has_perm(
            "resources.manage_resources"
        ),
    }


@login_required
def resource_list(request):
    if not (
        is_member(request.user)
        or request.user.has_perm(
            "resources.manage_resources"
        )
    ):
        raise PermissionDenied

    resources = list(
        visible_resources_for_user(
            request.user
        )
    )

    return render(
        request,
        "resources/resource_list.html",
        {
            "resources": resources,
            **resource_tabs_context(
                request.user
            ),
        },
    )


@login_required
@permission_required(
    "resources.manage_resources",
    raise_exception=True,
)
def manage_resources(request):
    resources = (
        Resource.objects
        .select_related("created_by")
        .order_by(
            "sort_order",
            "title",
            "pk",
        )
    )

    return render(
        request,
        "resources/resource_manage_list.html",
        {
            "resources": resources,
        },
    )


@login_required
@permission_required(
    "resources.manage_resources",
    raise_exception=True,
)
def manage_resource_detail(
    request,
    resource_id,
):
    resource = get_object_or_404(
        Resource,
        pk=resource_id,
    )

    targets = (
        resource.targets
        .select_related(*TARGET_SELECTORS)
        .all()
    )

    eligible_ids = set(
        User.objects.filter(
            account_status=AccountStatus.MEMBER,
            is_active=True,
        ).values_list(
            "pk",
            flat=True,
        )
    )

    if (
        resource.visibility
        == Resource.Visibility.CUSTOM
    ):
        eligible_ids &= (
            resolve_resource_include_targets(
                resource
            )
        )

    elif (
        resource.visibility
        != Resource.Visibility.MEMBERS
    ):
        eligible_ids.clear()

    eligible_ids -= (
        resolve_resource_exclude_targets(
            resource
        )
    )

    if not resource.is_active:
        eligible_ids.clear()

    audience = list(
        User.objects.filter(
            pk__in=eligible_ids,
        ).order_by(
            "display_name",
            "username",
            "pk",
        )
    )

    return render(
        request,
        "resources/resource_manage_detail.html",
        {
            "resource": resource,
            "targets": targets,
            "audience": audience,
            "audience_count": len(audience),
        },
    )


def save_resource(
    request,
    resource,
):
    old_value = (
        resource_values(resource)
        if resource.pk
        else None
    )

    form = ResourceForm(
        request.POST,
        request.FILES,
        instance=resource,
    )

    formset = ResourceTargetFormSet(
        request.POST,
        instance=resource,
        prefix="targets",
    )

    form_valid = form.is_valid()

    if form_valid:
        formset.instance.visibility = (
            form.cleaned_data["visibility"]
        )

    targets_valid = formset.is_valid()

    if form_valid and targets_valid:
        with transaction.atomic():
            changed_resource = form.save(
                commit=False
            )

            if not changed_resource.pk:
                changed_resource.created_by = (
                    request.user
                )

            changed_resource.save()

            formset.instance = (
                changed_resource
            )

            formset.save()

            record_resource_change(
                request,
                changed_resource,
                (
                    AuditLog.Action.UPDATE
                    if old_value is not None
                    else AuditLog.Action.CREATE
                ),
                old_value,
            )

        messages.success(
            request,
            "Resource saved.",
        )

        return redirect(
            "resources:manage_detail",
            resource_id=changed_resource.pk,
        )

    return render(
        request,
        "resources/resource_form.html",
        {
            "form": form,
            "target_formset": formset,
            "resource": (
                resource
                if resource.pk
                else None
            ),
        },
    )


@login_required
@permission_required(
    "resources.manage_resources",
    raise_exception=True,
)
@require_http_methods(["GET", "POST"])
def create_resource(request):
    resource = Resource(
        created_by=request.user,
    )

    if request.method == "POST":
        return save_resource(
            request,
            resource,
        )

    return render(
        request,
        "resources/resource_form.html",
        {
            "form": ResourceForm(
                instance=resource,
            ),
            "target_formset": ResourceTargetFormSet(
                instance=resource,
                prefix="targets",
            ),
            "resource": None,
        },
    )


@login_required
@permission_required(
    "resources.manage_resources",
    raise_exception=True,
)
@require_http_methods(["GET", "POST"])
def edit_resource(
    request,
    resource_id,
):
    resource = get_object_or_404(
        Resource,
        pk=resource_id,
    )

    if request.method == "POST":
        return save_resource(
            request,
            resource,
        )

    return render(
        request,
        "resources/resource_form.html",
        {
            "form": ResourceForm(
                instance=resource,
            ),
            "target_formset": ResourceTargetFormSet(
                instance=resource,
                prefix="targets",
            ),
            "resource": resource,
        },
    )


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
