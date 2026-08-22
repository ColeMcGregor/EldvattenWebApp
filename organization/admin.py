from django.contrib import admin

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


@admin.register(CitizenshipClass)
class CitizenshipClassAdmin(admin.ModelAdmin):
    list_display = ("name", "is_assignable", "updated_at")
    list_filter = ("is_assignable",)
    search_fields = ("name",)


@admin.register(SocialRank)
class SocialRankAdmin(admin.ModelAdmin):
    list_display = ("name", "is_assignable", "updated_at")
    list_filter = ("is_assignable",)
    search_fields = ("name",)


@admin.register(Office)
class OfficeAdmin(admin.ModelAdmin):
    list_display = ("name", "is_assignable", "updated_at")
    list_filter = ("is_assignable",)
    search_fields = ("name",)


@admin.register(ChapterStatus)
class ChapterStatusAdmin(admin.ModelAdmin):
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
class ChapterAdmin(admin.ModelAdmin):
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
class HouseholdAdmin(admin.ModelAdmin):
    list_display = ("name", "is_assignable", "updated_at")
    list_filter = ("is_assignable",)
    search_fields = ("name",)


@admin.register(GovernanceBody)
class GovernanceBodyAdmin(admin.ModelAdmin):
    list_display = ("name", "is_assignable", "updated_at")
    list_filter = ("is_assignable",)
    search_fields = ("name",)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
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
class OrderRankAdmin(admin.ModelAdmin):
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
class CommunityGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "is_assignable", "updated_at")
    list_filter = ("is_assignable",)
    search_fields = ("name",)


@admin.register(HouseholdLeadershipType)
class HouseholdLeadershipTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "is_assignable", "updated_at")
    list_filter = ("is_assignable",)
    search_fields = ("name",)


@admin.register(CitizenshipRecord)
class CitizenshipRecordAdmin(admin.ModelAdmin):
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
class UserSocialRankAdmin(admin.ModelAdmin):
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
class UserOfficeAdmin(admin.ModelAdmin):
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
class HouseholdMembershipAdmin(admin.ModelAdmin):
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
class HouseholdLeadershipAdmin(admin.ModelAdmin):
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
class GovernanceMembershipAdmin(admin.ModelAdmin):
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
class OrderMembershipAdmin(admin.ModelAdmin):
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
class GroupMembershipAdmin(admin.ModelAdmin):
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
class InitiateSponsorshipAdmin(admin.ModelAdmin):
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