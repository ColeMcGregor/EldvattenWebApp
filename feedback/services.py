
from django.db import transaction

from audit.models import AuditLog
from audit.services import record_audit_event

from .models import BugReport


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

    return report
