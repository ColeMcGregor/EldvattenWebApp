from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        (
            "EldVatten Account",
            {
                "fields": (
                    "display_name",
                    "account_status",
                )
            },
        ),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        (
            "EldVatten Account",
            {
                "fields": (
                    "display_name",
                    "account_status",
                )
            },
        ),
    )

    list_display = (
        "username",
        "email",
        "display_name",
        "account_status",
        "is_staff",
        "is_active",
    )


admin.site.register(User, CustomUserAdmin)