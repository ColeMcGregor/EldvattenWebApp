from django.contrib import admin

from audit.models import AuditLog
from audit.services import record_audit_event

from .models import (
    ForumBoard,
    ForumBoardSubscription,
    ForumBoardTarget,
    ForumBoardThreadCreationTarget,
    ForumCategory,
    ForumDraft,
    ForumPost,
    ForumPostAttachment,
    ForumPostQuote,
    ForumPostReport,
    ForumThread,
    ForumThreadReadState,
    ForumThreadSubscription,
    ForumThreadTarget,
)


def get_audit_values(obj):
    values = {}

    skipped_fields = {
        "id",
        "created_at",
        "updated_at",
    }

    for field in obj._meta.fields:
        if field.name in skipped_fields:
            continue

        value = getattr(
            obj,
            field.name,
        )

        if field.is_relation and value is not None:
            values[field.name] = str(value)

        elif hasattr(
            value,
            "isoformat",
        ):
            values[field.name] = value.isoformat()

        else:
            values[field.name] = value

    return values


class AuditedModelAdmin(admin.ModelAdmin):
    def save_model(
        self,
        request,
        obj,
        form,
        change,
    ):
        old_value = None

        if change:
            old_obj = (
                self.model.objects
                .get(pk=obj.pk)
            )

            old_value = get_audit_values(
                old_obj
            )

        super().save_model(
            request,
            obj,
            form,
            change,
        )

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

    def delete_model(
        self,
        request,
        obj,
    ):
        old_value = get_audit_values(obj)

        target_id = obj.pk
        target_label = str(obj)
        target_type = obj._meta.verbose_name

        super().delete_model(
            request,
            obj,
        )

        record_audit_event(
            actor=request.user,
            request=request,
            action=AuditLog.Action.DELETE,
            target_type=target_type,
            target_id=target_id,
            target_label=target_label,
            old_value=old_value,
            new_value=None,
            source=AuditLog.Source.ADMIN,
            method=AuditLog.Method.MANUAL,
        )

    def delete_queryset(
        self,
        request,
        queryset,
    ):
        deleted_objects = [
            {
                "id": obj.pk,
                "label": str(obj),
                "type": obj._meta.verbose_name,
                "values": get_audit_values(obj),
            }
            for obj in queryset
        ]

        super().delete_queryset(
            request,
            queryset,
        )

        for deleted_object in deleted_objects:
            record_audit_event(
                actor=request.user,
                request=request,
                action=AuditLog.Action.DELETE,
                target_type=deleted_object["type"],
                target_id=deleted_object["id"],
                target_label=deleted_object["label"],
                old_value=deleted_object["values"],
                new_value=None,
                source=AuditLog.Source.ADMIN,
                method=AuditLog.Method.MANUAL,
            )


class HardDeleteAdminMixin:
    def has_delete_permission(
        self,
        request,
        obj=None,
    ):
        return request.user.has_perm(
            "community.hard_delete_forum_content"
        )


class CategoryManagerAdminMixin:
    def has_add_permission(
        self,
        request,
    ):
        return (
            request.user.has_perm(
                "community.manage_forum_categories"
            )
            or super().has_add_permission(request)
        )

    def has_change_permission(
        self,
        request,
        obj=None,
    ):
        return (
            request.user.has_perm(
                "community.manage_forum_categories"
            )
            or super().has_change_permission(
                request,
                obj,
            )
        )

    def has_view_permission(
        self,
        request,
        obj=None,
    ):
        return (
            request.user.has_perm(
                "community.manage_forum_categories"
            )
            or super().has_view_permission(
                request,
                obj,
            )
        )


class BoardManagerAdminMixin:
    def has_add_permission(
        self,
        request,
    ):
        return (
            request.user.has_perm(
                "community.manage_forum_boards"
            )
            or super().has_add_permission(request)
        )

    def has_change_permission(
        self,
        request,
        obj=None,
    ):
        return (
            request.user.has_perm(
                "community.manage_forum_boards"
            )
            or super().has_change_permission(
                request,
                obj,
            )
        )

    def has_view_permission(
        self,
        request,
        obj=None,
    ):
        return (
            request.user.has_perm(
                "community.manage_forum_boards"
            )
            or super().has_view_permission(
                request,
                obj,
            )
        )


class ModeratorAdminMixin:
    def has_add_permission(
        self,
        request,
    ):
        return (
            request.user.has_perm(
                "community.moderate_forum"
            )
            or super().has_add_permission(request)
        )

    def has_change_permission(
        self,
        request,
        obj=None,
    ):
        return (
            request.user.has_perm(
                "community.moderate_forum"
            )
            or super().has_change_permission(
                request,
                obj,
            )
        )

    def has_view_permission(
        self,
        request,
        obj=None,
    ):
        return (
            request.user.has_perm(
                "community.moderate_forum"
            )
            or request.user.has_perm(
                "community.view_archived_forum_content"
            )
            or super().has_view_permission(
                request,
                obj,
            )
        )


@admin.register(ForumCategory)
class ForumCategoryAdmin(
    CategoryManagerAdminMixin,
    HardDeleteAdminMixin,
    AuditedModelAdmin,
):
    list_display = (
        "name",
        "display_order",
        "archived_at",
        "archived_by",
        "created_at",
        "updated_at",
    )

    list_filter = (
        "archived_at",
        "created_at",
    )

    search_fields = (
        "name",
        "description",
    )

    ordering = (
        "display_order",
        "name",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    raw_id_fields = (
        "archived_by",
    )


@admin.register(ForumBoard)
class ForumBoardAdmin(
    BoardManagerAdminMixin,
    HardDeleteAdminMixin,
    AuditedModelAdmin,
):
    list_display = (
        "name",
        "category",
        "display_order",
        "thread_creation_policy",
        "is_locked",
        "archived_at",
        "created_at",
    )

    list_filter = (
        "category",
        "thread_creation_policy",
        "is_locked",
        "archived_at",
        "created_at",
    )

    search_fields = (
        "name",
        "description",
        "category__name",
    )

    ordering = (
        "category__display_order",
        "display_order",
        "name",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    raw_id_fields = (
        "locked_by",
        "archived_by",
    )


@admin.register(ForumBoardTarget)
class ForumBoardTargetAdmin(
    BoardManagerAdminMixin,
    AuditedModelAdmin,
):
    list_display = (
        "board",
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
        "created_at",
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
        "created_at",
    )

    search_fields = (
        "board__name",
        "user__username",
        "user__display_name",
    )

    ordering = (
        "board__name",
        "id",
    )

    readonly_fields = (
        "created_at",
    )

    raw_id_fields = (
        "board",
        "user",
    )


@admin.register(
    ForumBoardThreadCreationTarget
)
class ForumBoardThreadCreationTargetAdmin(
    BoardManagerAdminMixin,
    AuditedModelAdmin,
):
    list_display = (
        "board",
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
        "created_at",
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
        "created_at",
    )

    search_fields = (
        "board__name",
        "user__username",
        "user__display_name",
    )

    ordering = (
        "board__name",
        "id",
    )

    readonly_fields = (
        "created_at",
    )

    raw_id_fields = (
        "board",
        "user",
    )


@admin.register(ForumThread)
class ForumThreadAdmin(
    ModeratorAdminMixin,
    HardDeleteAdminMixin,
    AuditedModelAdmin,
):
    list_display = (
        "title",
        "board",
        "created_by",
        "is_pinned",
        "is_locked",
        "last_post_at",
        "archived_at",
        "created_at",
    )

    list_filter = (
        "board__category",
        "board",
        "is_pinned",
        "is_locked",
        "archived_at",
        "created_at",
    )

    search_fields = (
        "title",
        "created_by__username",
        "created_by__display_name",
        "board__name",
        "board__category__name",
    )

    ordering = (
        "-is_pinned",
        "-last_post_at",
        "-created_at",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
        "last_post_at",
    )

    raw_id_fields = (
        "board",
        "created_by",
        "pinned_by",
        "locked_by",
        "archived_by",
        "merged_into",
    )


@admin.register(ForumThreadTarget)
class ForumThreadTargetAdmin(
    ModeratorAdminMixin,
    AuditedModelAdmin,
):
    list_display = (
        "thread",
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
        "created_at",
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
        "created_at",
    )

    search_fields = (
        "thread__title",
        "user__username",
        "user__display_name",
    )

    ordering = (
        "thread__title",
        "id",
    )

    readonly_fields = (
        "created_at",
    )

    raw_id_fields = (
        "thread",
        "user",
    )


@admin.register(ForumPost)
class ForumPostAdmin(
    ModeratorAdminMixin,
    HardDeleteAdminMixin,
    AuditedModelAdmin,
):
    list_display = (
        "id",
        "thread",
        "author",
        "created_at",
        "edited_at",
        "archived_at",
    )

    list_filter = (
        "archived_at",
        "created_at",
        "edited_at",
    )

    search_fields = (
        "body",
        "thread__title",
        "author__username",
        "author__display_name",
    )

    ordering = (
        "-created_at",
        "-id",
    )

    readonly_fields = (
        "created_at",
    )

    raw_id_fields = (
        "thread",
        "author",
        "edited_by",
        "archived_by",
    )


@admin.register(ForumPostQuote)
class ForumPostQuoteAdmin(
    ModeratorAdminMixin,
    AuditedModelAdmin,
):
    list_display = (
        "post",
        "quoted_post",
        "created_at",
    )

    search_fields = (
        "post__body",
        "quoted_post__body",
        "post__thread__title",
        "quoted_post__thread__title",
    )

    ordering = (
        "-created_at",
    )

    readonly_fields = (
        "created_at",
    )

    raw_id_fields = (
        "post",
        "quoted_post",
    )


@admin.register(ForumPostAttachment)
class ForumPostAttachmentAdmin(
    ModeratorAdminMixin,
    AuditedModelAdmin,
):
    list_display = (
        "post",
        "label",
        "url",
        "display_order",
        "created_at",
    )

    search_fields = (
        "label",
        "url",
        "post__body",
        "post__thread__title",
    )

    ordering = (
        "post",
        "display_order",
        "id",
    )

    readonly_fields = (
        "created_at",
    )

    raw_id_fields = (
        "post",
    )


@admin.register(ForumThreadReadState)
class ForumThreadReadStateAdmin(
    AuditedModelAdmin
):
    list_display = (
        "user",
        "thread",
        "last_read_at",
        "updated_at",
    )

    search_fields = (
        "user__username",
        "user__display_name",
        "thread__title",
    )

    ordering = (
        "-updated_at",
    )

    readonly_fields = (
        "updated_at",
    )

    raw_id_fields = (
        "user",
        "thread",
    )


@admin.register(ForumThreadSubscription)
class ForumThreadSubscriptionAdmin(
    AuditedModelAdmin
):
    list_display = (
        "user",
        "thread",
        "created_at",
    )

    search_fields = (
        "user__username",
        "user__display_name",
        "thread__title",
    )

    ordering = (
        "-created_at",
    )

    readonly_fields = (
        "created_at",
    )

    raw_id_fields = (
        "user",
        "thread",
    )


@admin.register(ForumBoardSubscription)
class ForumBoardSubscriptionAdmin(
    AuditedModelAdmin
):
    list_display = (
        "user",
        "board",
        "created_at",
    )

    search_fields = (
        "user__username",
        "user__display_name",
        "board__name",
    )

    ordering = (
        "-created_at",
    )

    readonly_fields = (
        "created_at",
    )

    raw_id_fields = (
        "user",
        "board",
    )


@admin.register(ForumPostReport)
class ForumPostReportAdmin(
    ModeratorAdminMixin,
    HardDeleteAdminMixin,
    AuditedModelAdmin,
):
    list_display = (
        "post",
        "reporter",
        "status",
        "created_at",
        "reviewed_at",
        "reviewed_by",
    )

    list_filter = (
        "status",
        "created_at",
        "reviewed_at",
    )

    search_fields = (
        "post__body",
        "post__thread__title",
        "reporter__username",
        "reporter__display_name",
        "reason",
        "resolution_note",
    )

    ordering = (
        "status",
        "-created_at",
    )

    readonly_fields = (
        "created_at",
    )

    raw_id_fields = (
        "post",
        "reporter",
        "reviewed_by",
    )


@admin.register(ForumDraft)
class ForumDraftAdmin(
    AuditedModelAdmin
):
    list_display = (
        "id",
        "user",
        "draft_type",
        "title",
        "board",
        "thread",
        "created_at",
        "updated_at",
    )

    list_filter = (
        "draft_type",
        "created_at",
        "updated_at",
    )

    search_fields = (
        "title",
        "body",
        "user__username",
        "user__display_name",
        "board__name",
        "thread__title",
    )

    ordering = (
        "-updated_at",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    raw_id_fields = (
        "user",
        "board",
        "thread",
    )