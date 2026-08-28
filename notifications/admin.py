from django.contrib import admin

from .models import (
    Notification,
    PushSubscription,
)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "notification_type",
        "title",
        "push_requested",
        "source_type",
        "is_read",
        "created_at",
        "read_at",
    )

    list_filter = (
        "notification_type",
        "push_requested",
        "is_read",
        "source_type",
        "created_at",
    )

    search_fields = (
        "user__username",
        "user__display_name",
        "title",
        "message",
        "source_type",
        "source_id",
    )

    ordering = (
        "-created_at",
    )

    readonly_fields = (
        "user",
        "notification_type",
        "title",
        "message",
        "source_type",
        "source_id",
        "target_url",
        "push_requested",
        "is_read",
        "read_at",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(
        self,
        request,
        obj=None,
    ):
        return False


@admin.register(PushSubscription)
class PushSubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "device_name",
        "active",
        "paused_until",
        "created_at",
        "updated_at",
    )

    list_filter = (
        "active",
        "created_at",
        "updated_at",
    )

    search_fields = (
        "user__username",
        "user__display_name",
        "device_name",
        "endpoint",
    )

    ordering = (
        "-updated_at",
    )

    readonly_fields = (
        "user",
        "endpoint",
        "p256dh_key",
        "auth_key",
        "device_name",
        "active",
        "paused_until",
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