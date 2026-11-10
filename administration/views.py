
from datetime import date

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, render

from audit.models import AuditLog

from .permissions import (
    can_access_administration,
    has_any_permission,
)
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


def require_audit_access(user):
    if not has_any_permission(
        user,
        ("audit.view_auditlog",),
    ):
        raise PermissionDenied


def parse_filter_date(value):
    if not value:
        return None

    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


@login_required
def audit_log_list(request):
    require_audit_access(request.user)

    actor = request.GET.get("actor", "").strip()[:150]
    action = request.GET.get("action", "").strip()
    target_type = request.GET.get(
        "target_type",
        "",
    ).strip()[:100]
    source = request.GET.get("source", "").strip()

    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()

    valid_actions = {
        value
        for value, label in AuditLog.Action.choices
    }

    valid_sources = {
        value
        for value, label in AuditLog.Source.choices
    }

    if action not in valid_actions:
        action = ""

    if source not in valid_sources:
        source = ""

    start_date = parse_filter_date(date_from)
    end_date = parse_filter_date(date_to)

    logs = AuditLog.objects.select_related(
        "actor",
    ).all()

    if actor:
        logs = logs.filter(
            Q(actor_label__icontains=actor)
            | Q(actor__username__icontains=actor)
        )

    if action:
        logs = logs.filter(
            action=action,
        )

    if target_type:
        logs = logs.filter(
            target_type__icontains=target_type,
        )

    if source:
        logs = logs.filter(
            source=source,
        )

    if start_date:
        logs = logs.filter(
            recorded_at__date__gte=start_date,
        )

    if end_date:
        logs = logs.filter(
            recorded_at__date__lte=end_date,
        )

    logs = logs.order_by(
        "-recorded_at",
        "-pk",
    )

    paginator = Paginator(
        logs,
        50,
    )

    page = paginator.get_page(
        request.GET.get("page"),
    )

    query_parameters = request.GET.copy()
    query_parameters.pop("page", None)

    return render(
        request,
        "administration/audit_logs.html",
        {
            "page": page,
            "logs": page.object_list,
            "action_choices": AuditLog.Action.choices,
            "source_choices": AuditLog.Source.choices,
            "filters": {
                "actor": actor,
                "action": action,
                "target_type": target_type,
                "source": source,
                "date_from": date_from,
                "date_to": date_to,
            },
            "filter_query": query_parameters.urlencode(),
        },
    )


@login_required
def audit_log_detail(request, log_id):
    require_audit_access(request.user)

    log = get_object_or_404(
        AuditLog.objects.select_related("actor"),
        pk=log_id,
    )

    old_values = (
        log.old_value
        if isinstance(log.old_value, dict)
        else {}
    )

    new_values = (
        log.new_value
        if isinstance(log.new_value, dict)
        else {}
    )

    changed_fields = []

    for field in sorted(
        old_values.keys() | new_values.keys()
    ):
        old_present = field in old_values
        new_present = field in new_values

        old_value = old_values.get(field)
        new_value = new_values.get(field)

        if (
            old_present != new_present
            or old_value != new_value
        ):
            changed_fields.append({
                "field": field,
                "old_present": old_present,
                "new_present": new_present,
                "old_value": old_value,
                "new_value": new_value,
            })

    return render(
        request,
        "administration/audit_log_detail.html",
        {
            "log": log,
            "changed_fields": changed_fields,
        },
    )
