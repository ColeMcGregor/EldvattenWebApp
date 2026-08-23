from datetime import datetime, time

from django.contrib import admin
from django.forms.models import model_to_dict
from django.utils import timezone

from audit.models import AuditLog
from audit.services import record_audit_event

from .models import (
    Chapter,
    ChapterStatus,
    CitizenshipClass,
    CitizenshipRecord,
    CommunityGroup,
    GovernanceBody,
    GovernanceMembership,
    GroupMembership,
    Household,
    HouseholdLeadership,
    HouseholdLeadershipType,
    HouseholdMembership,
    InitiateSponsorship,
    Office,
    Order,
    OrderMembership,
    OrderRank,
    SocialRank,
    UserOffice,
    UserSocialRank,
)


class AuditedAdmin(admin.ModelAdmin):
    audit_source = AuditLog.Source.ADMIN

    def get_audit_values(self, obj):
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

    def get_effective_at(self, obj):
        started_at = getattr(obj, "started_at", None)

        if not started_at:
            return None

        effective_at = datetime.combine(started_at, time.min)

        if timezone.is_naive(effective_at):
            effective_at = timezone.make_aware(effective_at)

        return effective_at

    def save_model(self, request, obj, form, change):
        old_value = None

        if change:
            old_obj = type(obj).objects.get(pk=obj.pk)
            old_value = self.get_audit_values(old_obj)

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
            new_value=self.get_audit_values(obj),
            effective_at=self.get_effective_at(obj),
            source=self.audit_source,
            method=AuditLog.Method.MANUAL,
        )

    def delete_model(self, request, obj):
        old_value = self.get_audit_values(obj)
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
            source=self.audit_source,
            method=AuditLog.Method.MANUAL,
        )


@admin.register(CitizenshipClass)
class CitizenshipClassAdmin(AuditedAdmin):
    list_display = ("name", "is_assignable", "updated_at")
    list_filter = ("is_assignable",)
    search_fields = ("name",)


@admin.register(SocialRank)
class SocialRankAdmin(AuditedAdmin):
    list_display = ("name", "is_assignable", "updated_at")
    list_filter = ("is_assignable",)
    search_fields = ("name",)


@admin.register(Office)
class OfficeAdmin(AuditedAdmin):
    list_display = ("name", "is_assignable", "updated_at")
    list_filter = ("is_assignable",)
    search_fields = ("name",)


@admin.register(ChapterStatus)
class ChapterStatusAdmin(AuditedAdmin):
    list_display = (
        "name",
        "allows_new_citizens",
        "is_selectable",
        "updated_at",
    )
    list_filter = (
        "allows_new_citizens",
        "is_selectable",
    )
    search_fields = ("name",)


@admin.register(Chapter)
class ChapterAdmin(AuditedAdmin):
    list_display = (
        "name",
        "status",
        "allows_new_citizens",
        "updated_at",
    )
    list_filter = ("status",)
    search_fields = ("name",)

    @admin.display(boolean=True, description="Allows new citizens")
    def allows_new_citizens(self, obj):
        return obj.status.allows_new_citizens


@admin.register(Household)
class HouseholdAdmin(AuditedAdmin):
    list_display = ("name", "is_assignable", "updated_at")
    list_filter = ("is_assignable",)
    search_fields = ("name",)


@admin.register(GovernanceBody)
class GovernanceBodyAdmin(AuditedAdmin):
    list_display = ("name", "is_assignable", "updated_at")
    list_filter = ("is_assignable",)
    search_fields = ("name",)


@admin.register(Order)
class OrderAdmin(AuditedAdmin):
    list_display = (
        "name",
        "uses_ranks",
        "is_assignable",
        "updated_at",
    )
    list_filter = (
        "uses_ranks",
        "is_assignable",
    )
    search_fields = ("name",)


@admin.register(OrderRank)
class OrderRankAdmin(AuditedAdmin):
    list_display = (
        "name",
        "rank_order",
        "is_assignable",
        "updated_at",
    )
    list_filter = ("is_assignable",)
    search_fields = ("name",)
    ordering = (
        "rank_order",
        "name",
    )


@admin.register(CommunityGroup)
class CommunityGroupAdmin(AuditedAdmin):
    list_display = ("name", "is_assignable", "updated_at")
    list_filter = ("is_assignable",)
    search_fields = ("name",)


@admin.register(HouseholdLeadershipType)
class HouseholdLeadershipTypeAdmin(AuditedAdmin):
    list_display = ("name", "is_assignable", "updated_at")
    list_filter = ("is_assignable",)
    search_fields = ("name",)


@admin.register(CitizenshipRecord)
class CitizenshipRecordAdmin(AuditedAdmin):
    list_display = (
        "user",
        "citizenship_class",
        "chapter",
        "started_at",
        "ended_at",
        "changed_by",
    )
    list_filter = (
        "citizenship_class",
        "chapter",
    )
    search_fields = (
        "user__username",
        "user__display_name",
    )


@admin.register(UserSocialRank)
class UserSocialRankAdmin(AuditedAdmin):
    list_display = (
        "user",
        "social_rank",
        "started_at",
        "ended_at",
        "changed_by",
    )
    list_filter = ("social_rank",)
    search_fields = (
        "user__username",
        "user__display_name",
    )


@admin.register(UserOffice)
class UserOfficeAdmin(AuditedAdmin):
    list_display = (
        "user",
        "office",
        "chapter",
        "started_at",
        "ended_at",
        "changed_by",
    )
    list_filter = (
        "office",
        "chapter",
    )
    search_fields = (
        "user__username",
        "user__display_name",
    )


@admin.register(HouseholdMembership)
class HouseholdMembershipAdmin(AuditedAdmin):
    list_display = (
        "user",
        "household",
        "started_at",
        "ended_at",
        "changed_by",
    )
    list_filter = ("household",)
    search_fields = (
        "user__username",
        "user__display_name",
    )


@admin.register(HouseholdLeadership)
class HouseholdLeadershipAdmin(AuditedAdmin):
    list_display = (
        "user",
        "household",
        "leadership_type",
        "started_at",
        "ended_at",
        "changed_by",
    )
    list_filter = (
        "household",
        "leadership_type",
    )
    search_fields = (
        "user__username",
        "user__display_name",
    )


@admin.register(GovernanceMembership)
class GovernanceMembershipAdmin(AuditedAdmin):
    list_display = (
        "user",
        "governance_body",
        "started_at",
        "ended_at",
        "changed_by",
    )
    list_filter = ("governance_body",)
    search_fields = (
        "user__username",
        "user__display_name",
    )


@admin.register(OrderMembership)
class OrderMembershipAdmin(AuditedAdmin):
    list_display = (
        "user",
        "order",
        "order_rank",
        "started_at",
        "ended_at",
        "changed_by",
    )
    list_filter = (
        "order",
        "order_rank",
    )
    search_fields = (
        "user__username",
        "user__display_name",
    )


@admin.register(GroupMembership)
class GroupMembershipAdmin(AuditedAdmin):
    list_display = (
        "user",
        "community_group",
        "started_at",
        "ended_at",
        "changed_by",
    )
    list_filter = ("community_group",)
    search_fields = (
        "user__username",
        "user__display_name",
    )


@admin.register(InitiateSponsorship)
class InitiateSponsorshipAdmin(AuditedAdmin):
    list_display = (
        "initiate",
        "sponsor",
        "sponsor_type",
        "started_at",
        "ended_at",
        "changed_by",
    )
    list_filter = ("sponsor_type",)
    search_fields = (
        "initiate__username",
        "initiate__display_name",
        "sponsor__username",
        "sponsor__display_name",
    )