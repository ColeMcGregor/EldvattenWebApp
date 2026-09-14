from django.contrib import admin

from audit.models import AuditLog
from audit.services import record_audit_event

from .models import Action, ActionAssignment, ActionTarget
from .services import sync_action_assignments


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


class ActionTargetInline(admin.StackedInline):
    model = ActionTarget
    extra = 1

    fields = (
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


class ActionAssignmentInline(admin.TabularInline):
    model = ActionAssignment
    extra = 0

    fields = (
        "user",
        "status",
        "is_active",
        "assigned_at",
        "unassigned_at",
        "opened_at",
        "completed_at",
    )

    readonly_fields = (
        "user",
        "assigned_at",
        "unassigned_at",
    )

    can_delete = False


@admin.register(Action)
class ActionAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "created_by",
        "is_required",
        "deadline",
        "created_at",
    )

    list_filter = (
        "is_required",
        "deadline",
        "created_at",
    )

    search_fields = (
        "title",
        "instructions",
        "created_by__username",
        "created_by__display_name",
    )

    filter_horizontal = (
        "linked_threads",
    )

    ordering = (
        "deadline",
        "-created_at",
    )

    inlines = (
        ActionTargetInline,
        ActionAssignmentInline,
    )

    actions = (
        "sync_assignments",
    )

    def save_model(
        self,
        request,
        obj,
        form,
        change,
    ):
        old_value = None

        if change:
            old_action = Action.objects.get(
                pk=obj.pk,
            )
            old_value = action_values(
                old_action,
            )

        super().save_model(
            request,
            obj,
            form,
            change,
        )

        new_value = action_values(obj)

        if not change:
            audit_action = AuditLog.Action.CREATE
        else:
            audit_action = AuditLog.Action.UPDATE

        record_audit_event(
            action=audit_action,
            target_type="Action",
            target_id=obj.id,
            target_label=str(obj),
            actor=request.user,
            request=request,
            old_value=old_value,
            new_value=new_value,
            source=AuditLog.Source.ADMIN,
            method=AuditLog.Method.MANUAL,
        )

    def save_related(
        self,
        request,
        form,
        formsets,
        change,
    ):
        super().save_related(
            request,
            form,
            formsets,
            change,
        )

        sync_action_assignments(
            form.instance,
            actor=request.user,
            request=request,
            source=AuditLog.Source.ADMIN,
            method=AuditLog.Method.MANUAL,
        )

    def delete_model(
        self,
        request,
        obj,
    ):
        old_value = action_values(obj)

        record_audit_event(
            action=AuditLog.Action.DELETE,
            target_type="Action",
            target_id=obj.id,
            target_label=str(obj),
            actor=request.user,
            request=request,
            old_value=old_value,
            new_value=None,
            source=AuditLog.Source.ADMIN,
            method=AuditLog.Method.MANUAL,
        )

        super().delete_model(
            request,
            obj,
        )

    @admin.action(
        description=(
            "Synchronize action assignments "
            "with current targets"
        )
    )
    def sync_assignments(
        self,
        request,
        queryset,
    ):
        activated_count = 0
        deactivated_count = 0

        for action in queryset:
            (
                activated_assignments,
                deactivated_assignments,
            ) = sync_action_assignments(
                action,
                actor=request.user,
                request=request,
                source=AuditLog.Source.ADMIN,
                method=AuditLog.Method.MANUAL,
            )

            activated_count += len(
                activated_assignments
            )
            deactivated_count += len(
                deactivated_assignments
            )

        self.message_user(
            request,
            (
                f"Activated {activated_count} "
                f"assignment(s) and deactivated "
                f"{deactivated_count} assignment(s)."
            ),
        )


@admin.register(ActionTarget)
class ActionTargetAdmin(admin.ModelAdmin):
    list_display = (
        "action",
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

    list_filter = (
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

    search_fields = (
        "action__title",
        "user__username",
        "user__display_name",
    )

    def save_model(
        self,
        request,
        obj,
        form,
        change,
    ):
        old_value = None

        if change:
            old_target = ActionTarget.objects.get(
                pk=obj.pk,
            )
            old_value = target_values(
                old_target,
            )

        super().save_model(
            request,
            obj,
            form,
            change,
        )

        if change:
            audit_action = AuditLog.Action.UPDATE
        else:
            audit_action = AuditLog.Action.CREATE

        record_audit_event(
            action=audit_action,
            target_type="ActionTarget",
            target_id=obj.id,
            target_label=str(obj),
            actor=request.user,
            request=request,
            old_value=old_value,
            new_value=target_values(obj),
            source=AuditLog.Source.ADMIN,
            method=AuditLog.Method.MANUAL,
        )

        sync_action_assignments(
            obj.action,
            actor=request.user,
            request=request,
            source=AuditLog.Source.ADMIN,
            method=AuditLog.Method.MANUAL,
        )

    def delete_model(
        self,
        request,
        obj,
    ):
        old_value = target_values(obj)
        action = obj.action

        record_audit_event(
            action=AuditLog.Action.DELETE,
            target_type="ActionTarget",
            target_id=obj.id,
            target_label=str(obj),
            actor=request.user,
            request=request,
            old_value=old_value,
            new_value=None,
            source=AuditLog.Source.ADMIN,
            method=AuditLog.Method.MANUAL,
        )

        super().delete_model(
            request,
            obj,
        )

        sync_action_assignments(
            action,
            actor=request.user,
            request=request,
            source=AuditLog.Source.ADMIN,
            method=AuditLog.Method.MANUAL,
        )


@admin.register(ActionAssignment)
class ActionAssignmentAdmin(admin.ModelAdmin):
    list_display = (
        "action",
        "user",
        "status",
        "is_active",
        "assigned_at",
        "unassigned_at",
        "opened_at",
        "completed_at",
    )

    list_filter = (
        "status",
        "is_active",
        "assigned_at",
        "unassigned_at",
        "opened_at",
        "completed_at",
    )

    search_fields = (
        "action__title",
        "user__username",
        "user__display_name",
    )

    ordering = (
        "-assigned_at",
    )

    def save_model(
        self,
        request,
        obj,
        form,
        change,
    ):
        old_value = None

        if change:
            old_assignment = (
                ActionAssignment.objects.get(
                    pk=obj.pk,
                )
            )
            old_value = assignment_values(
                old_assignment,
            )

        super().save_model(
            request,
            obj,
            form,
            change,
        )

        if change:
            audit_action = AuditLog.Action.UPDATE
        else:
            audit_action = AuditLog.Action.ASSIGN

        record_audit_event(
            action=audit_action,
            target_type="ActionAssignment",
            target_id=obj.id,
            target_label=str(obj),
            actor=request.user,
            request=request,
            old_value=old_value,
            new_value=assignment_values(obj),
            source=AuditLog.Source.ADMIN,
            method=AuditLog.Method.MANUAL,
        )

    def delete_model(
        self,
        request,
        obj,
    ):
        old_value = assignment_values(obj)

        record_audit_event(
            action=AuditLog.Action.REMOVE,
            target_type="ActionAssignment",
            target_id=obj.id,
            target_label=str(obj),
            actor=request.user,
            request=request,
            old_value=old_value,
            new_value=None,
            source=AuditLog.Source.ADMIN,
            method=AuditLog.Method.MANUAL,
        )

        super().delete_model(
            request,
            obj,
        )