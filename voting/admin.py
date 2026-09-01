from django.contrib import admin
from django.core.exceptions import ValidationError

from audit.models import AuditLog
from audit.services import record_audit_event

from .models import (
    Vote,
    VoteComment,
    VoteEligibleUser,
    VoteEligibilityTarget,
    VoteOption,
    VoteResponse,
)
from .services import (
    close_vote,
    get_vote_participation_count,
    get_vote_response_count,
    get_vote_tally,
    open_vote,
    preview_vote_eligibility,
)


def vote_values(vote):
    return {
        "title": vote.title,
        "description": vote.description,
        "status": vote.status,
        "approval_rule": vote.approval_rule,
        "is_anonymous": vote.is_anonymous,
        "requires_quorum": vote.requires_quorum,
        "quorum_numerator": vote.quorum_numerator,
        "quorum_denominator": vote.quorum_denominator,
        "requires_all_responses": vote.requires_all_responses,
        "opens_at": (
            vote.opens_at.isoformat()
            if vote.opens_at
            else None
        ),
        "closes_at": (
            vote.closes_at.isoformat()
            if vote.closes_at
            else None
        ),
        "opened_at": (
            vote.opened_at.isoformat()
            if vote.opened_at
            else None
        ),
        "closed_at": (
            vote.closed_at.isoformat()
            if vote.closed_at
            else None
        ),
        "created_by_id": vote.created_by_id,
    }


def option_values(option):
    return {
        "vote_id": option.vote_id,
        "label": option.label,
        "sort_order": option.sort_order,
    }


def eligibility_target_values(target):
    return {
        "vote_id": target.vote_id,
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


def eligible_user_values(eligible_user):
    return {
        "vote_id": eligible_user.vote_id,
        "user_id": eligible_user.user_id,
        "has_responded": eligible_user.has_responded,
        "added_at": (
            eligible_user.added_at.isoformat()
            if eligible_user.added_at
            else None
        ),
    }


def comment_values(comment):
    return {
        "vote_id": comment.vote_id,
        "author_id": comment.author_id,
        "body": comment.body,
        "created_at": (
            comment.created_at.isoformat()
            if comment.created_at
            else None
        ),
        "updated_at": (
            comment.updated_at.isoformat()
            if comment.updated_at
            else None
        ),
    }


class VoteOptionInline(admin.TabularInline):
    model = VoteOption
    extra = 2

    fields = (
        "label",
        "sort_order",
    )


class VoteEligibilityTargetInline(admin.StackedInline):
    model = VoteEligibilityTarget
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


class VoteEligibleUserInline(admin.TabularInline):
    model = VoteEligibleUser
    extra = 0

    fields = (
        "user",
        "has_responded",
        "added_at",
    )

    readonly_fields = (
        "user",
        "has_responded",
        "added_at",
    )

    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class VoteCommentInline(admin.TabularInline):
    model = VoteComment
    extra = 0

    fields = (
        "author",
        "body",
        "created_at",
        "updated_at",
    )

    readonly_fields = (
        "author",
        "body",
        "created_at",
        "updated_at",
    )

    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Vote)
class VoteAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "status",
        "is_anonymous",
        "approval_rule",
        "requires_quorum",
        "requires_all_responses",
        "opens_at",
        "closes_at",
        "created_by",
    )

    list_filter = (
        "status",
        "is_anonymous",
        "approval_rule",
        "requires_quorum",
        "requires_all_responses",
        "opens_at",
        "closes_at",
        "created_at",
    )

    search_fields = (
        "title",
        "description",
        "created_by__username",
        "created_by__display_name",
    )

    ordering = (
        "-created_at",
    )

    readonly_fields = (
        "opened_at",
        "closed_at",
        "created_at",
        "updated_at",
        "participation_summary",
        "tally_summary",
    )

    inlines = (
        VoteOptionInline,
        VoteEligibilityTargetInline,
        VoteEligibleUserInline,
        VoteCommentInline,
    )

    actions = (
        "preview_eligibility",
        "open_selected_votes",
        "close_selected_votes",
    )

    def get_readonly_fields(self, request, obj=None):
        fields = list(
            super().get_readonly_fields(
                request,
                obj,
            )
        )

        if (
            obj is not None
            and obj.status != Vote.Status.DRAFT
        ):
            fields.append("is_anonymous")

        return tuple(fields)

    @admin.display(
        description="Participation"
    )
    def participation_summary(self, obj):
        if obj is None or not obj.pk:
            return "Not available"

        eligible_count = obj.eligible_users.count()
        participation_count = get_vote_participation_count(
            obj
        )

        return (
            f"{participation_count} of "
            f"{eligible_count} eligible voters responded"
        )

    @admin.display(
        description="Tally"
    )
    def tally_summary(self, obj):
        if obj is None or not obj.pk:
            return "Not available"

        tally = get_vote_tally(obj)

        if not tally:
            return "No responses"

        return " | ".join(
            f"{item['label']}: {item['response_count']}"
            for item in tally
        )

    def save_model(self, request, obj, form, change):
        old_value = None

        if change:
            old_vote = Vote.objects.get(
                pk=obj.pk,
            )
            old_value = vote_values(old_vote)

        if not obj.created_by_id:
            obj.created_by = request.user

        obj.full_clean()

        super().save_model(
            request,
            obj,
            form,
            change,
        )

        record_audit_event(
            action=(
                AuditLog.Action.UPDATE
                if change
                else AuditLog.Action.CREATE
            ),
            target_type="Vote",
            target_id=obj.id,
            target_label=str(obj),
            actor=request.user,
            request=request,
            old_value=old_value,
            new_value=vote_values(obj),
            source=AuditLog.Source.ADMIN,
            method=AuditLog.Method.MANUAL,
        )

    def delete_model(self, request, obj):
        old_value = vote_values(obj)

        record_audit_event(
            action=AuditLog.Action.DELETE,
            target_type="Vote",
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
        description="Preview current vote eligibility"
    )
    def preview_eligibility(self, request, queryset):
        for vote in queryset:
            users = preview_vote_eligibility(vote)

            names = [
                user.display_name or user.get_username()
                for user in users
            ]

            if names:
                preview = ", ".join(names)
            else:
                preview = "No eligible users"

            self.message_user(
                request,
                f"{vote.title}: {preview}",
            )

    @admin.action(
        description="Open selected votes"
    )
    def open_selected_votes(self, request, queryset):
        opened_count = 0

        for vote in queryset:
            old_value = vote_values(vote)

            try:
                opened_vote = open_vote(vote)

            except ValidationError as error:
                self.message_user(
                    request,
                    f"{vote.title}: {error}",
                    level="ERROR",
                )
                continue

            record_audit_event(
                action=AuditLog.Action.UPDATE,
                target_type="Vote",
                target_id=opened_vote.id,
                target_label=str(opened_vote),
                actor=request.user,
                request=request,
                old_value=old_value,
                new_value=vote_values(opened_vote),
                effective_at=opened_vote.opened_at,
                source=AuditLog.Source.ADMIN,
                method=AuditLog.Method.MANUAL,
                notes="Vote opened and eligibility snapshot created.",
            )

            for eligible_user in opened_vote.eligible_users.select_related(
                "user",
            ):
                record_audit_event(
                    action=AuditLog.Action.ASSIGN,
                    target_type="VoteEligibleUser",
                    target_id=eligible_user.id,
                    target_label=str(eligible_user),
                    actor=request.user,
                    request=request,
                    old_value=None,
                    new_value=eligible_user_values(
                        eligible_user
                    ),
                    effective_at=eligible_user.added_at,
                    source=AuditLog.Source.ADMIN,
                    method=AuditLog.Method.MANUAL,
                    notes="User added to frozen vote eligibility snapshot.",
                )

            opened_count += 1

        if opened_count:
            self.message_user(
                request,
                f"Opened {opened_count} vote(s).",
            )

    @admin.action(
        description="Close selected votes"
    )
    def close_selected_votes(self, request, queryset):
        closed_count = 0

        for vote in queryset:
            old_value = vote_values(vote)

            try:
                result = close_vote(vote)

            except ValidationError as error:
                self.message_user(
                    request,
                    f"{vote.title}: {error}",
                    level="ERROR",
                )
                continue

            vote.refresh_from_db()

            record_audit_event(
                action=AuditLog.Action.UPDATE,
                target_type="Vote",
                target_id=vote.id,
                target_label=str(vote),
                actor=request.user,
                request=request,
                old_value=old_value,
                new_value=vote_values(vote),
                effective_at=vote.closed_at,
                source=AuditLog.Source.ADMIN,
                method=AuditLog.Method.MANUAL,
                notes=(
                    "Vote closed. "
                    f"Result: {result['reason']}"
                ),
            )

            closed_count += 1

        if closed_count:
            self.message_user(
                request,
                f"Closed {closed_count} vote(s).",
            )


@admin.register(VoteOption)
class VoteOptionAdmin(admin.ModelAdmin):
    list_display = (
        "vote",
        "label",
        "sort_order",
    )

    list_filter = (
        "vote",
    )

    search_fields = (
        "vote__title",
        "label",
    )

    ordering = (
        "vote",
        "sort_order",
    )

    def save_model(self, request, obj, form, change):
        old_value = None

        if change:
            old_option = VoteOption.objects.get(
                pk=obj.pk,
            )
            old_value = option_values(old_option)

        super().save_model(
            request,
            obj,
            form,
            change,
        )

        record_audit_event(
            action=(
                AuditLog.Action.UPDATE
                if change
                else AuditLog.Action.CREATE
            ),
            target_type="VoteOption",
            target_id=obj.id,
            target_label=str(obj),
            actor=request.user,
            request=request,
            old_value=old_value,
            new_value=option_values(obj),
            source=AuditLog.Source.ADMIN,
            method=AuditLog.Method.MANUAL,
        )

    def delete_model(self, request, obj):
        old_value = option_values(obj)

        record_audit_event(
            action=AuditLog.Action.DELETE,
            target_type="VoteOption",
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


@admin.register(VoteEligibilityTarget)
class VoteEligibilityTargetAdmin(admin.ModelAdmin):
    list_display = (
        "vote",
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
        "vote__title",
        "user__username",
        "user__display_name",
    )

    def save_model(self, request, obj, form, change):
        old_value = None

        if change:
            old_target = VoteEligibilityTarget.objects.get(
                pk=obj.pk,
            )
            old_value = eligibility_target_values(
                old_target
            )

        super().save_model(
            request,
            obj,
            form,
            change,
        )

        record_audit_event(
            action=(
                AuditLog.Action.UPDATE
                if change
                else AuditLog.Action.CREATE
            ),
            target_type="VoteEligibilityTarget",
            target_id=obj.id,
            target_label=str(obj),
            actor=request.user,
            request=request,
            old_value=old_value,
            new_value=eligibility_target_values(obj),
            source=AuditLog.Source.ADMIN,
            method=AuditLog.Method.MANUAL,
        )

    def delete_model(self, request, obj):
        old_value = eligibility_target_values(obj)

        record_audit_event(
            action=AuditLog.Action.DELETE,
            target_type="VoteEligibilityTarget",
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


@admin.register(VoteEligibleUser)
class VoteEligibleUserAdmin(admin.ModelAdmin):
    list_display = (
        "vote",
        "user",
        "has_responded",
        "added_at",
    )

    list_filter = (
        "vote",
        "has_responded",
        "added_at",
    )

    search_fields = (
        "vote__title",
        "user__username",
        "user__display_name",
    )

    readonly_fields = (
        "vote",
        "user",
        "has_responded",
        "added_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(
        self,
        request,
        obj=None,
    ):
        return False

    def has_delete_permission(
        self,
        request,
        obj=None,
    ):
        return False


@admin.register(VoteResponse)
class VoteResponseAdmin(admin.ModelAdmin):
    list_display = (
        "vote_name",
        "voter",
        "option",
        "submitted_at",
        "updated_at",
    )

    list_filter = (
        "option__vote",
        "option",
    )

    search_fields = (
        "option__vote__title",
        "eligibility__user__username",
        "eligibility__user__display_name",
    )

    readonly_fields = (
        "vote_name",
        "voter",
        "option",
        "submitted_at",
        "updated_at",
    )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .filter(
                option__vote__is_anonymous=False,
            )
            .select_related(
                "option",
                "option__vote",
                "eligibility",
                "eligibility__user",
            )
        )

    @admin.display(
        description="Vote"
    )
    def vote_name(self, obj):
        return obj.option.vote

    @admin.display(
        description="Voter"
    )
    def voter(self, obj):
        if obj.eligibility_id is None:
            return "Anonymous"

        return obj.eligibility.user

    def has_add_permission(self, request):
        return False

    def has_change_permission(
        self,
        request,
        obj=None,
    ):
        return False

    def has_delete_permission(
        self,
        request,
        obj=None,
    ):
        return False


@admin.register(VoteComment)
class VoteCommentAdmin(admin.ModelAdmin):
    list_display = (
        "vote",
        "author",
        "created_at",
        "updated_at",
    )

    list_filter = (
        "vote",
        "created_at",
    )

    search_fields = (
        "vote__title",
        "author__username",
        "author__display_name",
        "body",
    )

    readonly_fields = (
        "vote",
        "author",
        "body",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(
        self,
        request,
        obj=None,
    ):
        return False

    def has_delete_permission(
        self,
        request,
        obj=None,
    ):
        return False