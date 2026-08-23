from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from organization.models import CommunityGroup


class Post(models.Model):
    class Visibility(models.TextChoices):
        PUBLIC = "PUBLIC", "Public"
        GUESTS = "GUESTS", "Guests"
        MEMBERS = "MEMBERS", "Members"
        SELECTED_GROUPS = "SELECTED_GROUPS", "Selected Groups"

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="community_posts",
    )

    body = models.TextField()

    visibility = models.CharField(
        max_length=20,
        choices=Visibility.choices,
        default=Visibility.MEMBERS,
    )

    visible_to_groups = models.ManyToManyField(
        CommunityGroup,
        blank=True,
        related_name="visible_posts",
    )

    is_official = models.BooleanField(default=False)
    is_pinned = models.BooleanField(default=False)
    is_locked = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Post by {self.author} at {self.created_at}"


class Comment(models.Model):
    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name="comments",
    )

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="community_comments",
    )

    body = models.TextField()

    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="replies",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]

    def clean(self):
        if self.parent is None:
            return

        if self.parent.post_id != self.post_id:
            raise ValidationError(
                {
                    "parent": "A reply must belong to the same post."
                }
            )

        if self.parent.parent_id is not None:
            raise ValidationError(
                {
                    "parent": "Replies can only be one level deep."
                }
            )

    def __str__(self):
        return f"Comment by {self.author} on post {self.post_id}"