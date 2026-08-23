from django.contrib import admin

from audit.models import AuditLog
from audit.services import record_audit_event

from .models import Comment, Post


def get_audit_values(obj):
    values = {}
    skipped_fields = {"id", "created_at", "updated_at"}

    for field in obj._meta.fields:
        if field.name in skipped_fields:
            continue

        value = getattr(obj, field.name)

        if field.is_relation and value is not None:
            values[field.name] = str(value)
        elif hasattr(value, "isoformat"):
            values[field.name] = value.isoformat()
        else:
            values[field.name] = value

    return values


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = (
        "author",
        "visibility",
        "is_official",
        "is_pinned",
        "is_locked",
        "created_at",
    )

    list_filter = (
        "visibility",
        "is_official",
        "is_pinned",
        "is_locked",
        "created_at",
    )

    search_fields = (
        "author__username",
        "author__display_name",
        "body",
    )

    filter_horizontal = (
        "visible_to_groups",
    )

    ordering = (
        "-created_at",
    )

    def save_model(self, request, obj, form, change):
        old_value = None

        if change:
            old_obj = Post.objects.get(pk=obj.pk)
            old_value = get_audit_values(old_obj)

        super().save_model(request, obj, form, change)

        record_audit_event(
            actor=request.user,
            request=request,
            action=(
                AuditLog.Action.UPDATE
                if change
                else AuditLog.Action.CREATE
            ),
            target_type=obj._meta.verbose_name,
            target_id=obj.pk,
            target_label=str(obj),
            old_value=old_value,
            new_value=get_audit_values(obj),
            source=AuditLog.Source.ADMIN,
            method=AuditLog.Method.MANUAL,
        )

    def save_related(self, request, form, formsets, change):
        obj = form.instance

        old_groups = set()

        if obj.pk:
            old_groups = set(
                obj.visible_to_groups.values_list(
                    "name",
                    flat=True,
                )
            )

        super().save_related(
            request,
            form,
            formsets,
            change,
        )

        new_groups = set(
            obj.visible_to_groups.values_list(
                "name",
                flat=True,
            )
        )

        if old_groups != new_groups:
            record_audit_event(
                actor=request.user,
                request=request,
                action=AuditLog.Action.UPDATE,
                target_type=obj._meta.verbose_name,
                target_id=obj.pk,
                target_label=str(obj),
                old_value={
                    "visible_to_groups": sorted(old_groups),
                },
                new_value={
                    "visible_to_groups": sorted(new_groups),
                },
                source=AuditLog.Source.ADMIN,
                method=AuditLog.Method.MANUAL,
            )

    def delete_model(self, request, obj):
        old_value = get_audit_values(obj)
        old_value["visible_to_groups"] = list(
            obj.visible_to_groups.values_list(
                "name",
                flat=True,
            )
        )

        target_id = obj.pk
        target_label = str(obj)
        target_type = obj._meta.verbose_name

        super().delete_model(request, obj)

        record_audit_event(
            actor=request.user,
            request=request,
            action=AuditLog.Action.DELETE,
            target_type=target_type,
            target_id=target_id,
            target_label=target_label,
            old_value=old_value,
            source=AuditLog.Source.ADMIN,
            method=AuditLog.Method.MANUAL,
        )


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = (
        "author",
        "post",
        "parent",
        "created_at",
    )

    list_filter = (
        "created_at",
    )

    search_fields = (
        "author__username",
        "author__display_name",
        "body",
        "post__body",
    )

    ordering = (
        "created_at",
    )

    def save_model(self, request, obj, form, change):
        old_value = None

        if change:
            old_obj = Comment.objects.get(pk=obj.pk)
            old_value = get_audit_values(old_obj)

        super().save_model(request, obj, form, change)

        record_audit_event(
            actor=request.user,
            request=request,
            action=(
                AuditLog.Action.UPDATE
                if change
                else AuditLog.Action.CREATE
            ),
            target_type=obj._meta.verbose_name,
            target_id=obj.pk,
            target_label=str(obj),
            old_value=old_value,
            new_value=get_audit_values(obj),
            source=AuditLog.Source.ADMIN,
            method=AuditLog.Method.MANUAL,
        )

    def delete_model(self, request, obj):
        old_value = get_audit_values(obj)

        target_id = obj.pk
        target_label = str(obj)
        target_type = obj._meta.verbose_name

        super().delete_model(request, obj)

        record_audit_event(
            actor=request.user,
            request=request,
            action=AuditLog.Action.DELETE,
            target_type=target_type,
            target_id=target_id,
            target_label=target_label,
            old_value=old_value,
            source=AuditLog.Source.ADMIN,
            method=AuditLog.Method.MANUAL,
        )