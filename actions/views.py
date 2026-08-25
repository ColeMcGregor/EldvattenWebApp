from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.forms import inlineformset_factory
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.models import AccountStatus
from audit.models import AuditLog
from audit.services import record_audit_event

from .forms import ActionForm, ActionTargetForm
from .models import Action, ActionAssignment, ActionTarget
from .services import sync_action_assignments


ActionTargetFormSet = inlineformset_factory(
    Action,
    ActionTarget,
    form=ActionTargetForm,
    extra=1,
    can_delete=True,
)


def is_member(user):
    return (
        user.is_authenticated
        and user.is_active
        and user.account_status == AccountStatus.MEMBER
    )


def action_values(action):
    return {
        "title": action.title,
        "instructions": action.instructions,
        "external_url": action.external_url,
        "deadline": (
            action.deadline.isoformat()
            if action.deadline
            else None
        ),
        "is_required": action.is_required,
        "created_by_id": action.created_by_id,
        "linked_post_ids": list(
            action.linked_posts.values_list(
                "id",
                flat=True,
            )
        ),
    }


def target_values(target):
    return {
        "action_id": target.action_id,
        "user_id": target.user_id,
        "citizenship_class_id": target.citizenship_class_id,
        "social_rank_id": target.social_rank_id,
        "office_id": target.office_id,
        "chapter_id": target.chapter_id,
        "household_id": target.household_id,
        "governance_body_id": target.governance_body_id,
        "order_id": target.order_id,
        "order_rank_id": target.order_rank_id,
        "community_group_id": target.community_group_id,
        "household_leadership_type_id": (
            target.household_leadership_type_id
        ),
    }


def assignment_values(assignment):
    return {
        "action_id": assignment.action_id,
        "user_id": assignment.user_id,
        "status": assignment.status,
        "is_active": assignment.is_active,
        "assigned_at": (
            assignment.assigned_at.isoformat()
            if assignment.assigned_at
            else None
        ),
        "unassigned_at": (
            assignment.unassigned_at.isoformat()
            if assignment.unassigned_at
            else None
        ),
        "opened_at": (
            assignment.opened_at.isoformat()
            if assignment.opened_at
            else None
        ),
        "completed_at": (
            assignment.completed_at.isoformat()
            if assignment.completed_at
            else None
        ),
    }


@login_required
def action_list(request):
    if not is_member(request.user):
        raise PermissionDenied

    assignments = (
        ActionAssignment.objects.filter(
            user=request.user,
            is_active=True,
        )
        .select_related(
            "action",
            "action__created_by",
        )
        .order_by(
            "status",
            "action__deadline",
            "-assigned_at",
        )
    )

    return render(
        request,
        "actions/action_list.html",
        {
            "assignments": assignments,
        },
    )


@login_required
def action_detail(request, action_id):
    if not is_member(request.user):
        raise PermissionDenied

    assignment = get_object_or_404(
        ActionAssignment.objects.select_related(
            "action",
            "action__created_by",
        ).prefetch_related(
            "action__linked_posts",
        ),
        action_id=action_id,
        user=request.user,
        is_active=True,
    )

    if assignment.status == ActionAssignment.Status.NOT_STARTED:
        old_value = assignment_values(assignment)

        assignment.mark_opened()

        record_audit_event(
            action=AuditLog.Action.UPDATE,
            target_type="ActionAssignment",
            target_id=assignment.id,
            target_label=str(assignment),
            actor=request.user,
            request=request,
            old_value=old_value,
            new_value=assignment_values(assignment),
            effective_at=assignment.opened_at,
            source=AuditLog.Source.WEB_APP,
            method=AuditLog.Method.MANUAL,
            notes="Member opened assigned action.",
        )

    return render(
        request,
        "actions/action_detail.html",
        {
            "action": assignment.action,
            "assignment": assignment,
        },
    )


@login_required
@permission_required(
    "actions.add_action",
    raise_exception=True,
)
def action_create(request):
    if request.method == "POST":
        form = ActionForm(request.POST)

        if form.is_valid():
            action = form.save(commit=False)
            action.created_by = request.user

            target_formset = ActionTargetFormSet(
                request.POST,
                instance=action,
            )

            if target_formset.is_valid():
                action.save()
                form.save_m2m()

                target_formset.instance = action
                targets = target_formset.save()

                record_audit_event(
                    action=AuditLog.Action.CREATE,
                    target_type="Action",
                    target_id=action.id,
                    target_label=str(action),
                    actor=request.user,
                    request=request,
                    old_value=None,
                    new_value=action_values(action),
                    effective_at=action.created_at,
                    source=AuditLog.Source.WEB_APP,
                    method=AuditLog.Method.MANUAL,
                )

                for target in targets:
                    record_audit_event(
                        action=AuditLog.Action.CREATE,
                        target_type="ActionTarget",
                        target_id=target.id,
                        target_label=str(target),
                        actor=request.user,
                        request=request,
                        old_value=None,
                        new_value=target_values(target),
                        effective_at=target.created_at,
                        source=AuditLog.Source.WEB_APP,
                        method=AuditLog.Method.MANUAL,
                    )

                activated_assignments, deactivated_assignments = (
                    sync_action_assignments(
                        action,
                        actor=request.user,
                        request=request,
                        source=AuditLog.Source.WEB_APP,
                        method=AuditLog.Method.MANUAL,
                    )
                )

                messages.success(
                    request,
                    (
                        f"Action created. "
                        f"{len(activated_assignments)} assignment(s) activated."
                    ),
                )

                return redirect(
                    "actions:manage_detail",
                    action_id=action.id,
                )

        else:
            target_formset = ActionTargetFormSet(
                request.POST,
            )

    else:
        form = ActionForm()
        target_formset = ActionTargetFormSet()

    return render(
        request,
        "actions/action_form.html",
        {
            "form": form,
            "target_formset": target_formset,
            "page_title": "Create Action",
        },
    )


@login_required
@permission_required(
    "actions.change_action",
    raise_exception=True,
)
def action_edit(request, action_id):
    action = get_object_or_404(
        Action,
        id=action_id,
    )

    if request.method == "POST":
        old_action_value = action_values(action)

        old_target_values = {
            target.id: target_values(target)
            for target in action.targets.all()
        }

        form = ActionForm(
            request.POST,
            instance=action,
        )

        target_formset = ActionTargetFormSet(
            request.POST,
            instance=action,
        )

        if form.is_valid() and target_formset.is_valid():
            form.save()
            target_formset.save()

            action.refresh_from_db()

            new_action_value = action_values(action)

            if old_action_value != new_action_value:
                record_audit_event(
                    action=AuditLog.Action.UPDATE,
                    target_type="Action",
                    target_id=action.id,
                    target_label=str(action),
                    actor=request.user,
                    request=request,
                    old_value=old_action_value,
                    new_value=new_action_value,
                    source=AuditLog.Source.WEB_APP,
                    method=AuditLog.Method.MANUAL,
                )

            current_targets = {
                target.id: target
                for target in action.targets.all()
            }

            for target_id, target in current_targets.items():
                new_value = target_values(target)
                old_value = old_target_values.get(target_id)

                if old_value is None:
                    record_audit_event(
                        action=AuditLog.Action.CREATE,
                        target_type="ActionTarget",
                        target_id=target.id,
                        target_label=str(target),
                        actor=request.user,
                        request=request,
                        old_value=None,
                        new_value=new_value,
                        effective_at=target.created_at,
                        source=AuditLog.Source.WEB_APP,
                        method=AuditLog.Method.MANUAL,
                    )

                elif old_value != new_value:
                    record_audit_event(
                        action=AuditLog.Action.UPDATE,
                        target_type="ActionTarget",
                        target_id=target.id,
                        target_label=str(target),
                        actor=request.user,
                        request=request,
                        old_value=old_value,
                        new_value=new_value,
                        source=AuditLog.Source.WEB_APP,
                        method=AuditLog.Method.MANUAL,
                    )

            for target_id, old_value in old_target_values.items():
                if target_id not in current_targets:
                    record_audit_event(
                        action=AuditLog.Action.DELETE,
                        target_type="ActionTarget",
                        target_id=target_id,
                        target_label=f"Target for {action}",
                        actor=request.user,
                        request=request,
                        old_value=old_value,
                        new_value=None,
                        source=AuditLog.Source.WEB_APP,
                        method=AuditLog.Method.MANUAL,
                    )

            activated_assignments, deactivated_assignments = (
                sync_action_assignments(
                    action,
                    actor=request.user,
                    request=request,
                    source=AuditLog.Source.WEB_APP,
                    method=AuditLog.Method.MANUAL,
                )
            )

            messages.success(
                request,
                (
                    f"Action updated. "
                    f"{len(activated_assignments)} assignment(s) activated and "
                    f"{len(deactivated_assignments)} assignment(s) deactivated."
                ),
            )

            return redirect(
                "actions:manage_detail",
                action_id=action.id,
            )

    else:
        form = ActionForm(
            instance=action,
        )

        target_formset = ActionTargetFormSet(
            instance=action,
        )

    return render(
        request,
        "actions/action_form.html",
        {
            "form": form,
            "target_formset": target_formset,
            "page_title": "Edit Action",
            "editing": True,
        },
    )


@login_required
@permission_required(
    "actions.view_action",
    raise_exception=True,
)
def action_manage_detail(request, action_id):
    action = get_object_or_404(
        Action.objects.select_related(
            "created_by",
        ).prefetch_related(
            "targets",
            "assignments__user",
            "linked_posts",
        ),
        id=action_id,
    )

    assignments = action.assignments.select_related(
        "user",
    ).order_by(
        "-is_active",
        "status",
        "user__display_name",
        "user__username",
    )

    return render(
        request,
        "actions/action_manage_detail.html",
        {
            "action": action,
            "targets": action.targets.all(),
            "assignments": assignments,
        },
    )


@login_required
@permission_required(
    "actions.view_action",
    raise_exception=True,
)
def action_manage_list(request):
    actions = (
        Action.objects.select_related(
            "created_by",
        )
        .prefetch_related(
            "targets",
            "assignments",
        )
        .all()
    )

    return render(
        request,
        "actions/action_manage_list.html",
        {
            "actions": actions,
        },
    )


@login_required
@require_POST
def action_complete(request, action_id):
    if not is_member(request.user):
        raise PermissionDenied

    assignment = get_object_or_404(
        ActionAssignment,
        action_id=action_id,
        user=request.user,
        is_active=True,
    )

    if assignment.status != ActionAssignment.Status.COMPLETED:
        old_value = assignment_values(assignment)

        assignment.mark_completed()

        record_audit_event(
            action=AuditLog.Action.UPDATE,
            target_type="ActionAssignment",
            target_id=assignment.id,
            target_label=str(assignment),
            actor=request.user,
            request=request,
            old_value=old_value,
            new_value=assignment_values(assignment),
            effective_at=assignment.completed_at,
            source=AuditLog.Source.WEB_APP,
            method=AuditLog.Method.MANUAL,
            notes="Member completed assigned action.",
        )

    messages.success(
        request,
        "Action marked complete.",
    )

    return redirect(
        "actions:detail",
        action_id=action_id,
    )


@login_required
@permission_required(
    "actions.change_action",
    raise_exception=True,
)
@require_POST
def action_resolve_assignments(request, action_id):
    action = get_object_or_404(
        Action,
        id=action_id,
    )

    activated_assignments, deactivated_assignments = (
        sync_action_assignments(
            action,
            actor=request.user,
            request=request,
            source=AuditLog.Source.WEB_APP,
            method=AuditLog.Method.MANUAL,
        )
    )

    messages.success(
        request,
        (
            f"{len(activated_assignments)} assignment(s) activated and "
            f"{len(deactivated_assignments)} assignment(s) deactivated."
        ),
    )

    return redirect(
        "actions:manage_detail",
        action_id=action.id,
    )


@login_required
@permission_required(
    "actions.delete_action",
    raise_exception=True,
)
def action_delete(request, action_id):
    action = get_object_or_404(
        Action,
        id=action_id,
    )

    if request.method == "POST":
        old_value = action_values(action)
        target_id = action.id
        target_label = str(action)

        record_audit_event(
            action=AuditLog.Action.DELETE,
            target_type="Action",
            target_id=target_id,
            target_label=target_label,
            actor=request.user,
            request=request,
            old_value=old_value,
            new_value=None,
            source=AuditLog.Source.WEB_APP,
            method=AuditLog.Method.MANUAL,
        )

        action.delete()

        messages.success(
            request,
            "Action deleted.",
        )

        return redirect(
            "actions:manage_list",
        )

    return render(
        request,
        "actions/action_confirm_delete.html",
        {
            "action": action,
        },
    )