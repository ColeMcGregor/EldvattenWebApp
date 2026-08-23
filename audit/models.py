from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    class Action(models.TextChoices):
        CREATE = "CREATE", "Create"
        UPDATE = "UPDATE", "Update"
        DELETE = "DELETE", "Delete"
        ASSIGN = "ASSIGN", "Assign"
        REMOVE = "REMOVE", "Remove"
        APPROVE = "APPROVE", "Approve"
        REJECT = "REJECT", "Reject"
        SUSPEND = "SUSPEND", "Suspend"
        RESTORE = "RESTORE", "Restore"

    class Source(models.TextChoices):
        ADMIN = "ADMIN", "Django Admin"
        ORGANIZATION_SETUP = "ORGANIZATION_SETUP", "Organization Setup"
        MEMBER_MANAGEMENT = "MEMBER_MANAGEMENT", "Member Management"
        IMPORT = "IMPORT", "Import"
        SYSTEM = "SYSTEM", "System"
        API = "API", "API"

    class Method(models.TextChoices):
        MANUAL = "MANUAL", "Manual"
        AUTOMATIC = "AUTOMATIC", "Automatic"
        IMPORT = "IMPORT", "Import"
        API = "API", "API"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="audit_actions",
        blank=True,
        null=True,
    )
    actor_label = models.CharField(
        max_length=150,
        blank=True,
    )
    ip_address = models.GenericIPAddressField(
        blank=True,
        null=True,
    )

    action = models.CharField(
        max_length=20,
        choices=Action.choices,
    )

    target_type = models.CharField(max_length=100)
    target_id = models.CharField(
        max_length=100,
        blank=True,
    )
    target_label = models.CharField(
        max_length=255,
        blank=True,
    )

    old_value = models.JSONField(
        blank=True,
        null=True,
    )
    new_value = models.JSONField(
        blank=True,
        null=True,
    )

    effective_at = models.DateTimeField(
        blank=True,
        null=True,
    )
    recorded_at = models.DateTimeField(auto_now_add=True)

    source = models.CharField(
        max_length=30,
        choices=Source.choices,
    )
    method = models.CharField(
        max_length=20,
        choices=Method.choices,
    )

    request_path = models.CharField(
        max_length=500,
        blank=True,
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-recorded_at"]

    def __str__(self):
        actor = self.actor_label or str(self.actor) if self.actor else "System"
        target = self.target_label or self.target_type

        return f"{actor} - {self.get_action_display()} - {target}"