
from datetime import date

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.views.decorators.http import require_http_methods

from accounts.forms import (
    AccountActivationForm,
    AccountGroupForm,
    AccountStatusForm,
)
from accounts.models import AccountStatus
from accounts.services import (
    change_account_status,
    set_account_active,
    set_account_groups,
)
from audit.models import AuditLog
from feedback.forms import BugReportManagementForm
from feedback.models import BugReport
from feedback.services import update_bug_report

from .permissions import (
    can_access_administration,
    has_any_permission,
)
from .sections import (
    get_administration_sections,
    get_section_links,
)


User = get_user_model()


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


def require_bug_report_access(user):
    if not (
        user.is_authenticated
        and user.is_active
        and user.is_staff
        and user.is_superuser
    ):
        raise PermissionDenied


def require_account_access(user):
    if not has_any_permission(
        user,
        (
            "accounts.approve_membership",
            "accounts.change_user",
        ),
    ):
        raise PermissionDenied


def can_approve_membership(user):
    return has_any_permission(
        user,
        ("accounts.approve_membership",),
    )


def can_manage_account_status(user):
    return has_any_permission(
        user,
        ("accounts.change_user",),
    )


def can_manage_account_security(user):
    return (
        user.is_authenticated
        and user.is_active
        and user.is_staff
        and user.is_superuser
    )


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


@login_required
def bug_report_list(request):
    require_bug_report_access(request.user)

    status = request.GET.get(
        "status",
        "",
    ).strip()

    valid_statuses = {
        value
        for value, label in BugReport.Status.choices
    }

    if status not in valid_statuses:
        status = ""

    reports = BugReport.objects.select_related(
        "reporter",
    ).all()

    if status:
        reports = reports.filter(
            status=status,
        )

    reports = reports.order_by(
        "-created_at",
        "-pk",
    )

    paginator = Paginator(
        reports,
        25,
    )

    page = paginator.get_page(
        request.GET.get("page"),
    )

    query_parameters = request.GET.copy()
    query_parameters.pop("page", None)

    return render(
        request,
        "administration/bug_reports.html",
        {
            "page": page,
            "reports": page.object_list,
            "status_choices": BugReport.Status.choices,
            "selected_status": status,
            "filter_query": query_parameters.urlencode(),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def bug_report_detail(request, report_id):
    require_bug_report_access(request.user)

    report = get_object_or_404(
        BugReport.objects.select_related(
            "reporter",
        ),
        pk=report_id,
    )

    if request.method == "POST":
        form = BugReportManagementForm(
            request.POST,
            instance=report,
        )

        if form.is_valid():
            update_bug_report(
                report=report,
                status=form.cleaned_data["status"],
                admin_notes=form.cleaned_data["admin_notes"],
                request=request,
            )

            messages.success(
                request,
                "Bug report updated.",
            )

            return redirect(
                "administration:bug_report_detail",
                report_id=report.pk,
            )

    else:
        form = BugReportManagementForm(
            instance=report,
        )

    return render(
        request,
        "administration/bug_report_detail.html",
        {
            "report": report,
            "form": form,
        },
    )


@login_required
def account_list(request):
    require_account_access(request.user)

    search = request.GET.get(
        "search",
        "",
    ).strip()[:150]

    status = request.GET.get(
        "status",
        "",
    ).strip()

    role = request.GET.get(
        "role",
        "",
    ).strip()

    valid_statuses = {
        value
        for value, label in AccountStatus.choices
    }

    if status not in valid_statuses:
        status = ""

    if role not in {
        "",
        "member",
        "staff",
        "superuser",
    }:
        role = ""

    accounts = User.objects.all()

    if search:
        accounts = accounts.filter(
            Q(username__icontains=search)
            | Q(display_name__icontains=search)
            | Q(email__icontains=search)
        )

    if status:
        accounts = accounts.filter(
            account_status=status,
        )

    if role == "member":
        accounts = accounts.filter(
            is_staff=False,
            is_superuser=False,
        )

    elif role == "staff":
        accounts = accounts.filter(
            is_staff=True,
            is_superuser=False,
        )

    elif role == "superuser":
        accounts = accounts.filter(
            is_superuser=True,
        )

    accounts = accounts.order_by(
        "-date_joined",
        "-pk",
    )

    paginator = Paginator(
        accounts,
        25,
    )

    page = paginator.get_page(
        request.GET.get("page"),
    )

    query_parameters = request.GET.copy()
    query_parameters.pop("page", None)

    return render(
        request,
        "administration/accounts.html",
        {
            "page": page,
            "accounts": page.object_list,
            "status_choices": AccountStatus.choices,
            "filters": {
                "search": search,
                "status": status,
                "role": role,
            },
            "filter_query": query_parameters.urlencode(),
            "pending_count": User.objects.filter(
                account_status=AccountStatus.PENDING,
            ).count(),
            "member_count": User.objects.filter(
                account_status=AccountStatus.MEMBER,
            ).count(),
            "suspended_count": User.objects.filter(
                account_status=AccountStatus.SUSPENDED,
            ).count(),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def account_detail(request, user_id):
    require_account_access(request.user)

    account = get_object_or_404(
        User.objects.prefetch_related("groups"),
        pk=user_id,
    )

    allow_approval = can_approve_membership(
        request.user
    )

    allow_status_management = (
        can_manage_account_status(request.user)
    )

    allow_security_management = (
        can_manage_account_security(request.user)
    )

    status_form = AccountStatusForm(
        instance=account,
        actor=request.user,
    )

    activation_form = AccountActivationForm(
        instance=account,
    )

    group_form = AccountGroupForm(
        instance=account,
    )

    if request.method == "POST":
        action = request.POST.get(
            "action",
            "",
        )

        if action == "status":
            if not (
                allow_approval
                or allow_status_management
            ):
                raise PermissionDenied

            status_form = AccountStatusForm(
                request.POST,
                instance=account,
                actor=request.user,
            )

            if status_form.is_valid():
                change_account_status(
                    account=account,
                    status=status_form.cleaned_data[
                        "account_status"
                    ],
                    request=request,
                )

                messages.success(
                    request,
                    "Membership status updated.",
                )

                return redirect(
                    "administration:account_detail",
                    user_id=account.pk,
                )

        elif action == "activation":
            if not allow_security_management:
                raise PermissionDenied

            activation_form = AccountActivationForm(
                request.POST,
                instance=account,
            )

            if activation_form.is_valid():
                set_account_active(
                    account=account,
                    is_active=activation_form.cleaned_data[
                        "is_active"
                    ],
                    request=request,
                )

                messages.success(
                    request,
                    "Account activation updated.",
                )

                return redirect(
                    "administration:account_detail",
                    user_id=account.pk,
                )

        elif action == "groups":
            if not allow_security_management:
                raise PermissionDenied

            group_form = AccountGroupForm(
                request.POST,
                instance=account,
            )

            if group_form.is_valid():
                set_account_groups(
                    account=account,
                    groups=group_form.cleaned_data[
                        "groups"
                    ],
                    request=request,
                )

                messages.success(
                    request,
                    "Administrative roles updated.",
                )

                return redirect(
                    "administration:account_detail",
                    user_id=account.pk,
                )

        else:
            raise PermissionDenied

    account_audit_logs = []

    if has_any_permission(
        request.user,
        ("audit.view_auditlog",),
    ):
        account_audit_logs = (
            AuditLog.objects
            .filter(
                target_id=str(account.pk),
                target_type__in=(
                    "user account",
                    "application role",
                ),
            )
            .order_by(
                "-recorded_at",
                "-pk",
            )[:10]
        )

    return render(
        request,
        "administration/account_detail.html",
        {
            "account": account,
            "status_form": status_form,
            "activation_form": activation_form,
            "group_form": group_form,
            "allow_approval": allow_approval,
            "allow_status_management": (
                allow_status_management
            ),
            "allow_security_management": (
                allow_security_management
            ),
            "account_audit_logs": account_audit_logs,
        },
    )
