from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q

from organization.models import (
    Chapter,
    CitizenshipClass,
    CommunityGroup,
    GovernanceBody,
    Household,
    HouseholdLeadershipType,
    Office,
    Order,
    OrderRank,
    SocialRank,
)


class ForumTargetBase(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="+",
    )

    citizenship_class = models.ForeignKey(
        CitizenshipClass,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="+",
    )

    social_rank = models.ForeignKey(
        SocialRank,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="+",
    )

    office = models.ForeignKey(
        Office,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="+",
    )

    chapter = models.ForeignKey(
        Chapter,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="+",
    )

    household = models.ForeignKey(
        Household,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="+",
    )

    governance_body = models.ForeignKey(
        GovernanceBody,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="+",
    )

    order = models.ForeignKey(
        Order,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="+",
    )

    order_rank = models.ForeignKey(
        OrderRank,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="+",
    )

    community_group = models.ForeignKey(
        CommunityGroup,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="+",
    )

    household_leadership_type = models.ForeignKey(
        HouseholdLeadershipType,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="+",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        abstract = True
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(user__isnull=False)
                    | Q(citizenship_class__isnull=False)
                    | Q(social_rank__isnull=False)
                    | Q(office__isnull=False)
                    | Q(chapter__isnull=False)
                    | Q(household__isnull=False)
                    | Q(governance_body__isnull=False)
                    | Q(order__isnull=False)
                    | Q(order_rank__isnull=False)
                    | Q(community_group__isnull=False)
                    | Q(household_leadership_type__isnull=False)
                ),
                name="%(app_label)s_%(class)s_has_selector",
            ),
            models.CheckConstraint(
                condition=(
                    Q(user__isnull=True)
                    | (
                        Q(citizenship_class__isnull=True)
                        & Q(social_rank__isnull=True)
                        & Q(office__isnull=True)
                        & Q(chapter__isnull=True)
                        & Q(household__isnull=True)
                        & Q(governance_body__isnull=True)
                        & Q(order__isnull=True)
                        & Q(order_rank__isnull=True)
                        & Q(community_group__isnull=True)
                        & Q(household_leadership_type__isnull=True)
                    )
                ),
                name="%(app_label)s_%(class)s_user_exclusive",
            ),
        ]

    def clean(self):
        super().clean()

        target_field_ids = [
            self.user_id,
            self.citizenship_class_id,
            self.social_rank_id,
            self.office_id,
            self.chapter_id,
            self.household_id,
            self.governance_body_id,
            self.order_id,
            self.order_rank_id,
            self.community_group_id,
            self.household_leadership_type_id,
        ]

        if not any(target_field_ids):
            raise ValidationError(
                "A forum target must contain at least one selector."
            )

        if self.user_id is not None:
            organizational_field_ids = target_field_ids[1:]

            if any(organizational_field_ids):
                raise ValidationError(
                    "A specific user target cannot be combined "
                    "with organizational selectors."
                )


class ForumCategory(models.Model):
    name = models.CharField(
        max_length=150,
        unique=True,
    )

    description = models.TextField(
        blank=True,
    )

    display_order = models.PositiveIntegerField(
        default=0,
    )

    archived_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    archived_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="+",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = [
            "display_order",
            "name",
        ]
        default_permissions = (
            "add",
            "change",
            "view",
        )
        permissions = [
            (
                "manage_forum_categories",
                "Can manage forum categories",
            ),
        ]

    @property
    def is_archived(self):
        return self.archived_at is not None

    def __str__(self):
        return self.name


class ForumBoard(models.Model):
    class ThreadCreationPolicy(models.TextChoices):
        OPEN = "OPEN", "Open"
        TARGETED = "TARGETED", "Targeted"
        STAFF_ONLY = "STAFF_ONLY", "Staff only"

    category = models.ForeignKey(
        ForumCategory,
        on_delete=models.PROTECT,
        related_name="boards",
    )

    name = models.CharField(
        max_length=150,
    )

    description = models.TextField(
        blank=True,
    )

    display_order = models.PositiveIntegerField(
        default=0,
    )

    thread_creation_policy = models.CharField(
        max_length=20,
        choices=ThreadCreationPolicy.choices,
        default=ThreadCreationPolicy.OPEN,
    )

    is_locked = models.BooleanField(
        default=False,
    )

    locked_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    locked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="+",
    )

    archived_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    archived_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="+",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = [
            "display_order",
            "name",
        ]
        default_permissions = (
            "add",
            "change",
            "view",
        )
        permissions = [
            (
                "manage_forum_boards",
                "Can manage forum boards",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["category", "name"],
                name="unique_forum_board_name_per_category",
            ),
        ]
        indexes = [
            models.Index(
                fields=["category", "display_order", "name"],
                name="forum_board_order_idx",
            ),
        ]

    @property
    def is_archived(self):
        return self.archived_at is not None

    def __str__(self):
        return self.name


class ForumBoardTarget(ForumTargetBase):
    board = models.ForeignKey(
        ForumBoard,
        on_delete=models.CASCADE,
        related_name="targets",
    )

    def __str__(self):
        return f"Visibility target for board {self.board_id}"


class ForumBoardThreadCreationTarget(ForumTargetBase):
    board = models.ForeignKey(
        ForumBoard,
        on_delete=models.CASCADE,
        related_name="thread_creation_targets",
    )

    def __str__(self):
        return f"Thread creation target for board {self.board_id}"


class ForumThread(models.Model):
    board = models.ForeignKey(
        ForumBoard,
        on_delete=models.PROTECT,
        related_name="threads",
    )

    title = models.CharField(
        max_length=255,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="forum_threads_created",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    last_post_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    is_pinned = models.BooleanField(
        default=False,
    )

    pinned_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    pinned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="+",
    )

    is_locked = models.BooleanField(
        default=False,
    )

    locked_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    locked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="+",
    )

    archived_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    archived_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="+",
    )

    merged_into = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="merged_threads",
    )

    class Meta:
        default_permissions = (
            "add",
            "change",
            "view",
        )
        permissions = [
            (
                "moderate_forum",
                "Can moderate the forum",
            ),
            (
                "view_archived_forum_content",
                "Can view archived forum content",
            ),
            (
                "hard_delete_forum_content",
                "Can permanently delete forum content",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(merged_into__isnull=True)
                    | ~Q(merged_into=F("id"))
                ),
                name="forum_thread_not_merged_into_self",
            ),
        ]
        indexes = [
            models.Index(
                fields=["board", "-is_pinned", "-last_post_at"],
                name="forum_thread_sort_idx",
            ),
            models.Index(
                fields=["archived_at"],
                name="forum_thread_arch_idx",
            ),
        ]

    @property
    def is_archived(self):
        return self.archived_at is not None

    def clean(self):
        super().clean()

        if (
            self.pk is not None
            and self.merged_into_id == self.pk
        ):
            raise ValidationError(
                {
                    "merged_into": (
                        "A forum thread cannot be merged into itself."
                    )
                }
            )

    def __str__(self):
        return self.title


class ForumThreadTarget(ForumTargetBase):
    thread = models.ForeignKey(
        ForumThread,
        on_delete=models.CASCADE,
        related_name="targets",
    )

    def __str__(self):
        return f"Visibility target for thread {self.thread_id}"


class ForumPost(models.Model):
    thread = models.ForeignKey(
        ForumThread,
        on_delete=models.CASCADE,
        related_name="posts",
    )

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="forum_posts",
    )

    body = models.TextField()

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    edited_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    edited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="+",
    )

    archived_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    archived_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="+",
    )

    class Meta:
        ordering = [
            "created_at",
            "id",
        ]
        default_permissions = (
            "add",
            "change",
            "view",
        )
        indexes = [
            models.Index(
                fields=["thread", "created_at", "id"],
                name="forum_post_thread_idx",
            ),
            models.Index(
                fields=["archived_at"],
                name="forum_post_arch_idx",
            ),
        ]

    @property
    def is_archived(self):
        return self.archived_at is not None

    def __str__(self):
        return (
            f"Post {self.pk or 'unsaved'} "
            f"in thread {self.thread_id}"
        )


class ForumPostQuote(models.Model):
    post = models.ForeignKey(
        ForumPost,
        on_delete=models.CASCADE,
        related_name="quotes",
    )

    quoted_post = models.ForeignKey(
        ForumPost,
        on_delete=models.CASCADE,
        related_name="quoted_by",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["post", "quoted_post"],
                name="unique_forum_post_quote",
            ),
            models.CheckConstraint(
                condition=~Q(post=F("quoted_post")),
                name="forum_post_cannot_quote_self",
            ),
        ]

    def clean(self):
        super().clean()

        if (
            self.post_id is not None
            and self.post_id == self.quoted_post_id
        ):
            raise ValidationError(
                {
                    "quoted_post": (
                        "A forum post cannot quote itself."
                    )
                }
            )

    def __str__(self):
        return (
            f"Post {self.post_id} "
            f"quotes post {self.quoted_post_id}"
        )


class ForumPostAttachment(models.Model):
    post = models.ForeignKey(
        ForumPost,
        on_delete=models.CASCADE,
        related_name="attachments",
    )

    label = models.CharField(
        max_length=255,
        blank=True,
    )

    url = models.URLField(
        max_length=2048,
    )

    display_order = models.PositiveIntegerField(
        default=0,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = [
            "display_order",
            "id",
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["post", "url"],
                name="unique_forum_post_attachment_url",
            ),
        ]

    def __str__(self):
        if self.label:
            return self.label

        return self.url


class ForumThreadReadState(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="forum_thread_read_states",
    )

    thread = models.ForeignKey(
        ForumThread,
        on_delete=models.CASCADE,
        related_name="read_states",
    )

    last_read_at = models.DateTimeField()

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "thread"],
                name="unique_forum_thread_read_state",
            ),
        ]

    def __str__(self):
        return (
            f"Read state for user {self.user_id} "
            f"on thread {self.thread_id}"
        )


class ForumThreadSubscription(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="forum_thread_subscriptions",
    )

    thread = models.ForeignKey(
        ForumThread,
        on_delete=models.CASCADE,
        related_name="subscriptions",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "thread"],
                name="unique_forum_thread_subscription",
            ),
        ]

    def __str__(self):
        return (
            f"User {self.user_id} "
            f"follows thread {self.thread_id}"
        )


class ForumBoardSubscription(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="forum_board_subscriptions",
    )

    board = models.ForeignKey(
        ForumBoard,
        on_delete=models.CASCADE,
        related_name="subscriptions",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "board"],
                name="unique_forum_board_subscription",
            ),
        ]

    def __str__(self):
        return (
            f"User {self.user_id} "
            f"follows board {self.board_id}"
        )


class ForumPostReport(models.Model):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        RESOLVED = "RESOLVED", "Resolved"
        DISMISSED = "DISMISSED", "Dismissed"

    post = models.ForeignKey(
        ForumPost,
        on_delete=models.CASCADE,
        related_name="reports",
    )

    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="forum_post_reports",
    )

    reason = models.TextField()

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    reviewed_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="+",
    )

    resolution_note = models.TextField(
        blank=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["post", "reporter"],
                condition=Q(status="OPEN"),
                name="unique_open_forum_post_report",
            ),
        ]
        indexes = [
            models.Index(
                fields=["status", "created_at"],
                name="forum_report_status_idx",
            ),
        ]

    def clean(self):
        super().clean()

        if (
            self.reporter_id is not None
            and self.post_id is not None
            and self.post.author_id == self.reporter_id
        ):
            raise ValidationError(
                {
                    "reporter": (
                        "A user cannot report their own forum post."
                    )
                }
            )

    def __str__(self):
        return f"Report for post {self.post_id}"


class ForumDraft(models.Model):
    class DraftType(models.TextChoices):
        THREAD = "THREAD", "Thread"
        POST = "POST", "Post"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="forum_drafts",
    )

    draft_type = models.CharField(
        max_length=10,
        choices=DraftType.choices,
    )

    board = models.ForeignKey(
        ForumBoard,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="thread_drafts",
    )

    thread = models.ForeignKey(
        ForumThread,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="post_drafts",
    )

    title = models.CharField(
        max_length=255,
        blank=True,
    )

    body = models.TextField(
        blank=True,
    )

    target_data = models.JSONField(
        default=list,
        blank=True,
    )

    attachment_links = models.JSONField(
        default=list,
        blank=True,
    )

    quoted_post_ids = models.JSONField(
        default=list,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(
                        draft_type="THREAD",
                        board__isnull=False,
                        thread__isnull=True,
                    )
                    | Q(
                        draft_type="POST",
                        board__isnull=True,
                        thread__isnull=False,
                    )
                ),
                name="forum_draft_parent_matches_type",
            ),
        ]
        indexes = [
            models.Index(
                fields=["user", "-updated_at"],
                name="forum_draft_user_idx",
            ),
        ]

    def clean(self):
        super().clean()

        if self.draft_type == self.DraftType.THREAD:
            if (
                self.board_id is None
                or self.thread_id is not None
            ):
                raise ValidationError(
                    {
                        "board": (
                            "A thread draft must belong to a board."
                        ),
                        "thread": (
                            "A thread draft cannot belong to a thread."
                        ),
                    }
                )

        elif self.draft_type == self.DraftType.POST:
            if (
                self.thread_id is None
                or self.board_id is not None
            ):
                raise ValidationError(
                    {
                        "board": (
                            "A post draft cannot belong directly "
                            "to a board."
                        ),
                        "thread": (
                            "A post draft must belong to a thread."
                        ),
                    }
                )

    def __str__(self):
        return (
            f"{self.get_draft_type_display()} "
            f"draft for user {self.user_id}"
        )