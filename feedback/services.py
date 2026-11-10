
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.urls import reverse

from accounts.models import User
from audit.models import AuditLog
from audit.services import record_audit_event
from notifications.models import Notification
from notifications.services import create_notifications

from .models import BugReport
from .rate_limiting import consume_submission_quota


@transaction.atomic
def create_bug_report(
    *,
    report,
    request,
):
    if report.pk is not None:
        raise ValueError(
            "Only new bug reports can be submitted."
        )

    actor = (
        request.user
        if request.user.is_authenticated
        else None
    )

    report.reporter = actor
    report.status = BugReport.Status.NEW

    report.full_clean()

    consume_submission_quota(
        request=request,
    )

    report.save()

    record_audit_event(
        actor=actor,
        request=request,
        action=AuditLog.Action.CREATE,
        target_type="BugReport",
        target_id=report.pk,
        target_label=f"Bug Report #{report.pk}",
        old_value=None,
        new_value={
            "status": report.status,
        },
        source=AuditLog.Source.WEB_APP,
        method=AuditLog.Method.MANUAL,
    )

    administrators = User.objects.filter(
        is_active=True,
        is_staff=True,
        is_superuser=True,
    )

    create_notifications(
        recipients=administrators,
        notification_type=Notification.Type.SYSTEM,
        title=f"New Bug Report #{report.pk}",
        message=(
            "A new bug report has been submitted "
            "and is awaiting review."
        ),
        source_type="BugReport",
        source_id=report.pk,
        target_url=reverse(
            "administration:bug_report_detail",
            args=[report.pk],
        ),
    )

    return report


@transaction.atomic
def update_bug_report(
    *,
    report,
    status,
    admin_notes,
    request,
):
    user = request.user

    if not (
        user.is_authenticated
        and user.is_active
        and user.is_staff
        and user.is_superuser
    ):
        raise PermissionDenied

    report = (
        BugReport.objects
        .select_for_update()
        .get(pk=report.pk)
    )

    previous_status = report.status
    previous_notes = report.admin_notes

    status_changed = (
        previous_status != status
    )

    notes_changed = (
        previous_notes != admin_notes
    )

    if not status_changed and not notes_changed:
        return report

    report.status = status
    report.admin_notes = admin_notes

    report.full_clean()

    report.save(
        update_fields=[
            "status",
            "admin_notes",
            "updated_at",
        ]
    )

    record_audit_event(
        actor=user,
        request=request,
        action=AuditLog.Action.UPDATE,
        target_type="BugReport",
        target_id=report.pk,
        target_label=f"Bug Report #{report.pk}",
        old_value={
            "status": previous_status,
        },
        new_value={
            "status": report.status,
        },
        source=AuditLog.Source.WEB_APP,
        method=AuditLog.Method.MANUAL,
        notes=(
            "Internal notes updated."
            if notes_changed
            else ""
        ),
    )

    return report
