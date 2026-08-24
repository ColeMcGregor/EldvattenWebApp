from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.forms import inlineformset_factory
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.models import AccountStatus

from .forms import ActionForm, ActionTargetForm
from .models import Action, ActionAssignment, ActionTarget
from .services import create_action_assignments


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


@login_required
def action_list(request):
    if not is_member(request.user):
        raise PermissionDenied

    assignments = (
        ActionAssignment.objects.filter(
            user=request.user,
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
    )

    if assignment.status == ActionAssignment.Status.NOT_STARTED:
        assignment.mark_opened()

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
                target_formset.save()

                created_assignments = create_action_assignments(action)

                messages.success(
                    request,
                    (
                        f"Action created. "
                        f"{len(created_assignments)} assignment(s) created."
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
        form = ActionForm(
            request.POST,
            instance=action,
        )

        if form.is_valid():
            form.save()

            messages.success(
                request,
                "Action updated.",
            )

            return redirect(
                "actions:manage_detail",
                action_id=action.id,
            )

    else:
        form = ActionForm(
            instance=action,
        )

    return render(
        request,
        "actions/action_form.html",
        {
            "form": form,
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
    )

    assignment.mark_completed()

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
    "actions.add_action",
    raise_exception=True,
)
@require_POST
def action_resolve_assignments(request, action_id):
    action = get_object_or_404(
        Action,
        id=action_id,
    )

    created_assignments = create_action_assignments(action)

    messages.success(
        request,
        (
            f"{len(created_assignments)} new assignment(s) created."
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