from django.contrib import admin

from .models import Action, ActionAssignment, ActionTarget
from .services import create_action_assignments


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
        "opened_at",
        "completed_at",
        "assigned_at",
    )

    readonly_fields = (
        "user",
        "assigned_at",
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
        "linked_posts",
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
        "resolve_assignments",
    )

    @admin.action(
        description="Resolve targets and create assignments"
    )
    def resolve_assignments(self, request, queryset):
        created_count = 0

        for action in queryset:
            assignments = create_action_assignments(action)
            created_count += len(assignments)

        self.message_user(
            request,
            f"Created {created_count} new action assignments.",
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


@admin.register(ActionAssignment)
class ActionAssignmentAdmin(admin.ModelAdmin):
    list_display = (
        "action",
        "user",
        "status",
        "assigned_at",
        "opened_at",
        "completed_at",
    )

    list_filter = (
        "status",
        "assigned_at",
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
    