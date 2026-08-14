from django.contrib.auth.models import AbstractUser
from django.db import models

#These define the models for the accounts


# Account status options
class AccountStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    MEMBER = "MEMBER", "Member"
    SUSPENDED = "SUSPENDED", "Suspended"
    DISABLED = "DISABLED", "Disabled"

#changes to the django supplied AbstractUser, adds display name and account status.
class User(AbstractUser):
    display_name = models.CharField(
        max_length=150,
        blank=True,
    )

    account_status = models.CharField(
        max_length=20,
        choices=AccountStatus.choices,
        default=AccountStatus.PENDING,
    )

    class Meta:
        permissions = [
            ("approve_membership", "Can approve membership"),
        ]