from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = (
        "recorded_at",
        "actor_label",
        "action",
        "target_type",
        "target_label",
        "source",
        "method",
        "ip_address",
    )

    list_filter = (
        "action",
        "source",
        "method",
        "recorded_at",
    )

    search_fields = (
        "actor_label",
        "target_type",
        "target_id",
        "target_label",
        "request_path",
        "notes",
    )

    readonly_fields = (
        "actor",
        "actor_label",
        "ip_address",
        "action",
        "target_type",
        "target_id",
        "target_label",
        "old_value",
        "new_value",
        "effective_at",
        "recorded_at",
        "source",
        "method",
        "request_path",
        "notes",
    )

    ordering = ("-recorded_at",)

    

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return True

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        extra_context = extra_context or {}

        if object_id:
            extra_context["title"] = "View audit log"

        return super().changeform_view(
            request,
            object_id,
            form_url,
            extra_context,
        )