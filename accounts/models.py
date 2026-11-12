
from django.contrib.auth.models import AbstractUser
from django.db import models


# Account status options.
class AccountStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    MEMBER = "MEMBER", "Member"
    REJECTED = "REJECTED", "Rejected"
    SUSPENDED = "SUSPENDED", "Suspended"
    DISABLED = "DISABLED", "Disabled"


class User(AbstractUser):
    display_name = models.CharField(
        max_length=150,
        blank=True,
    )

    eldvatten_name = models.CharField(
        max_length=150,
        blank=True,
    )

    account_status = models.CharField(
        max_length=20,
        choices=AccountStatus.choices,
        default=AccountStatus.PENDING,
    )

    push_prompt_seen = models.BooleanField(
        default=False,
    )

    @property
    def community_name(self):
        return (
            self.eldvatten_name.strip()
            or self.display_name.strip()
            or self.get_full_name().strip()
            or self.username
        )

    class Meta:
        permissions = [
            ("approve_membership", "Can approve membership"),
        ]
