from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import F, Q
from django.urls import reverse
from django.utils import timezone

from accounts.models import AccountStatus, User
from notifications.models import Notification
from notifications.services import create_notifications
from organization.models import (
    CitizenshipRecord,
    GovernanceMembership,
    GroupMembership,
    HouseholdLeadership,
    HouseholdMembership,
    OrderMembership,
    UserOffice,
    UserSocialRank,
)

from .models import (
    ForumBoard,
    ForumBoardSubscription,
    ForumCategory,
    ForumDraft,
    ForumPost,
    ForumPostAttachment,
    ForumPostQuote,
    ForumPostReport,
    ForumThread,
    ForumThreadReadState,
    ForumThreadSubscription,
    ForumThreadTarget,
)


FORUM_READ_ACCOUNT_STATUSES = {
    AccountStatus.PENDING,
    AccountStatus.MEMBER,
}


def user_can_read_forum(user):
    return (
        user.is_authenticated
        and user.is_active
        and user.account_status in FORUM_READ_ACCOUNT_STATUSES
    )


def user_is_forum_member(user):
    return (
        user_can_read_forum(user)
        and user.account_status == AccountStatus.MEMBER
    )


def user_is_forum_moderator(user):
    return (
        user.is_authenticated
        and user.is_active
        and (
            user.is_superuser
            or user.has_perm("community.moderate_forum")
        )
    )


def user_can_view_archived_forum(user):
    return (
        user.is_authenticated
        and user.is_active
        and (
            user.is_superuser
            or user.has_perm(
                "community.view_archived_forum_content"
            )
        )
    )


def user_can_manage_forum_categories(user):
    return (
        user.is_authenticated
        and user.is_active
        and (
            user.is_superuser
            or user.has_perm(
                "community.manage_forum_categories"
            )
        )
    )


def user_can_manage_forum_boards(user):
    return (
        user.is_authenticated
        and user.is_active
        and (
            user.is_superuser
            or user.has_perm(
                "community.manage_forum_boards"
            )
        )
    )


def resolve_forum_targets(targets):
    def resolve_target(target):
        user_ids = set(
            User.objects.filter(
                account_status__in=FORUM_READ_ACCOUNT_STATUSES,
                is_active=True,
            ).values_list(
                "id",
                flat=True,
            )
        )

        if target.user_id is not None:
            if (
                target.user.is_active
                and target.user.account_status
                in FORUM_READ_ACCOUNT_STATUSES
            ):
                return {target.user_id}

            return set()

        if target.citizenship_class_id is not None:
            user_ids &= set(
                CitizenshipRecord.objects.filter(
                    citizenship_class_id=target.citizenship_class_id,
                    ended_at__isnull=True,
                ).values_list(
                    "user_id",
                    flat=True,
                )
            )

        if target.social_rank_id is not None:
            user_ids &= set(
                UserSocialRank.objects.filter(
                    social_rank_id=target.social_rank_id,
                    ended_at__isnull=True,
                ).values_list(
                    "user_id",
                    flat=True,
                )
            )

        if target.office_id is not None:
            office_records = UserOffice.objects.filter(
                office_id=target.office_id,
                ended_at__isnull=True,
            )

            if target.chapter_id is not None:
                office_records = office_records.filter(
                    chapter_id=target.chapter_id,
                )

            user_ids &= set(
                office_records.values_list(
                    "user_id",
                    flat=True,
                )
            )

        if target.chapter_id is not None:
            user_ids &= set(
                CitizenshipRecord.objects.filter(
                    chapter_id=target.chapter_id,
                    ended_at__isnull=True,
                ).values_list(
                    "user_id",
                    flat=True,
                )
            )

        if target.household_id is not None:
            user_ids &= set(
                HouseholdMembership.objects.filter(
                    household_id=target.household_id,
                    ended_at__isnull=True,
                ).values_list(
                    "user_id",
                    flat=True,
                )
            )

        if target.governance_body_id is not None:
            user_ids &= set(
                GovernanceMembership.objects.filter(
                    governance_body_id=target.governance_body_id,
                    ended_at__isnull=True,
                ).values_list(
                    "user_id",
                    flat=True,
                )
            )

        if target.order_id is not None:
            order_records = OrderMembership.objects.filter(
                order_id=target.order_id,
                ended_at__isnull=True,
            )

            if target.order_rank_id is not None:
                order_records = order_records.filter(
                    order_rank_id=target.order_rank_id,
                )

            user_ids &= set(
                order_records.values_list(
                    "user_id",
                    flat=True,
                )
            )

        elif target.order_rank_id is not None:
            user_ids &= set(
                OrderMembership.objects.filter(
                    order_rank_id=target.order_rank_id,
                    ended_at__isnull=True,
                ).values_list(
                    "user_id",
                    flat=True,
                )
            )

        if target.community_group_id is not None:
            user_ids &= set(
                GroupMembership.objects.filter(
                    community_group_id=target.community_group_id,
                    ended_at__isnull=True,
                ).values_list(
                    "user_id",
                    flat=True,
                )
            )

        if target.household_leadership_type_id is not None:
            leadership_records = HouseholdLeadership.objects.filter(
                leadership_type_id=(
                    target.household_leadership_type_id
                ),
                ended_at__isnull=True,
            )

            if target.household_id is not None:
                leadership_records = leadership_records.filter(
                    household_id=target.household_id,
                )

            user_ids &= set(
                leadership_records.values_list(
                    "user_id",
                    flat=True,
                )
            )

        return user_ids

    resolved_user_ids = set()

    for target in targets:
        resolved_user_ids.update(
            resolve_target(target)
        )

    return resolved_user_ids


def user_matches_forum_targets(user, targets):
    targets = list(targets)

    if not targets:
        return True

    return user.id in resolve_forum_targets(
        targets
    )


def user_can_access_board(
    user,
    board,
    *,
    include_archived=False,
):
    is_archived = (
        board.archived_at is not None
        or board.category.archived_at is not None
    )

    if is_archived:
        if not include_archived:
            return False

        if not user_can_view_archived_forum(user):
            return False

    if user_is_forum_moderator(user):
        return True

    if not user_can_read_forum(user):
        return False

    return user_matches_forum_targets(
        user,
        board.targets.all(),
    )


def user_can_access_thread(
    user,
    thread,
    *,
    include_archived=False,
):
    if not user_can_access_board(
        user,
        thread.board,
        include_archived=include_archived,
    ):
        return False

    if thread.archived_at is not None:
        if not include_archived:
            return False

        if not user_can_view_archived_forum(user):
            return False

    if user_is_forum_moderator(user):
        return True

    return user_matches_forum_targets(
        user,
        thread.targets.all(),
    )


def get_accessible_boards(
    user,
    *,
    include_archived=False,
):
    if (
        not user_can_read_forum(user)
        and not user_is_forum_moderator(user)
    ):
        return ForumBoard.objects.none()

    boards = (
        ForumBoard.objects
        .select_related("category")
        .prefetch_related("targets")
    )

    if not (
        include_archived
        and user_can_view_archived_forum(user)
    ):
        boards = boards.filter(
            archived_at__isnull=True,
            category__archived_at__isnull=True,
        )

    board_ids = [
        board.pk
        for board in boards
        if user_can_access_board(
            user,
            board,
            include_archived=include_archived,
        )
    ]

    return (
        ForumBoard.objects
        .filter(pk__in=board_ids)
        .select_related("category")
        .order_by(
            "category__display_order",
            "category__name",
            "display_order",
            "name",
        )
    )


def get_accessible_categories(
    user,
    *,
    include_archived=False,
):
    category_ids = (
        get_accessible_boards(
            user,
            include_archived=include_archived,
        )
        .values_list(
            "category_id",
            flat=True,
        )
        .distinct()
    )

    return ForumCategory.objects.filter(
        pk__in=category_ids,
    ).order_by(
        "display_order",
        "name",
    )


def get_accessible_threads(
    user,
    *,
    board=None,
    include_archived=False,
):
    if (
        not user_can_read_forum(user)
        and not user_is_forum_moderator(user)
    ):
        return ForumThread.objects.none()

    threads = (
        ForumThread.objects
        .select_related(
            "board",
            "board__category",
            "created_by",
        )
        .prefetch_related(
            "board__targets",
            "targets",
        )
    )

    if board is not None:
        threads = threads.filter(
            board=board,
        )

    if not (
        include_archived
        and user_can_view_archived_forum(user)
    ):
        threads = threads.filter(
            archived_at__isnull=True,
            board__archived_at__isnull=True,
            board__category__archived_at__isnull=True,
        )

    thread_ids = [
        thread.pk
        for thread in threads
        if user_can_access_thread(
            user,
            thread,
            include_archived=include_archived,
        )
    ]

    return (
        ForumThread.objects
        .filter(pk__in=thread_ids)
        .select_related(
            "board",
            "board__category",
            "created_by",
        )
        .order_by(
            "-is_pinned",
            F("last_post_at").desc(
                nulls_last=True,
            ),
            "-created_at",
        )
    )


def user_can_create_thread(user, board):
    moderator = user_is_forum_moderator(user)
    board_manager = user_can_manage_forum_boards(
        user
    )

    if (
        not moderator
        and not board_manager
        and not user_is_forum_member(user)
    ):
        return False

    if (
        board.archived_at is not None
        or board.category.archived_at is not None
    ):
        return False

    if board.is_locked and not moderator:
        return False

    if moderator or board_manager:
        return True

    if not user_can_access_board(user, board):
        return False

    if (
        board.thread_creation_policy
        == ForumBoard.ThreadCreationPolicy.OPEN
    ):
        return True

    if (
        board.thread_creation_policy
        == ForumBoard.ThreadCreationPolicy.STAFF_ONLY
    ):
        return False

    if (
        board.thread_creation_policy
        == ForumBoard.ThreadCreationPolicy.TARGETED
    ):
        return user_matches_forum_targets(
            user,
            board.thread_creation_targets.all(),
        )

    return False


def thread_creator_controls(user, thread):
    if thread.created_by_id != user.id:
        return False

    return not thread.posts.exclude(
        author_id=user.id,
    ).exists()


def user_can_change_thread(user, thread):
    if thread.archived_at is not None:
        return False

    if user_is_forum_moderator(user):
        return True

    if not user_is_forum_member(user):
        return False

    if thread.board.is_locked:
        return False

    if not user_can_access_thread(
        user,
        thread,
    ):
        return False

    return thread_creator_controls(
        user,
        thread,
    )


def user_can_archive_thread(user, thread):
    if thread.archived_at is not None:
        return False

    if user_is_forum_moderator(user):
        return True

    return user_can_change_thread(
        user,
        thread,
    )


def user_can_restore_thread(user, thread):
    if thread.archived_at is None:
        return False

    if user_is_forum_moderator(user):
        return True

    if not user_is_forum_member(user):
        return False

    if (
        thread.board.archived_at is not None
        or thread.board.category.archived_at is not None
        or thread.board.is_locked
    ):
        return False

    if not user_can_access_board(
        user,
        thread.board,
    ):
        return False

    if not user_matches_forum_targets(
        user,
        thread.targets.all(),
    ):
        return False

    return thread_creator_controls(
        user,
        thread,
    )


def user_can_add_post(user, thread):
    if (
        thread.archived_at is not None
        or thread.board.archived_at is not None
        or thread.board.category.archived_at is not None
    ):
        return False

    if user_is_forum_moderator(user):
        return True

    if not user_is_forum_member(user):
        return False

    if not user_can_access_thread(
        user,
        thread,
    ):
        return False

    return not (
        thread.is_locked
        or thread.board.is_locked
    )


def user_can_edit_post(user, post):
    if post.archived_at is not None:
        return False

    if user_is_forum_moderator(user):
        return True

    if (
        not user_is_forum_member(user)
        or post.author_id != user.id
    ):
        return False

    if not user_can_access_thread(
        user,
        post.thread,
    ):
        return False

    return not (
        post.thread.is_locked
        or post.thread.board.is_locked
    )


def user_can_archive_post(user, post):
    if post.archived_at is not None:
        return False

    if user_is_forum_moderator(user):
        return True

    return user_can_edit_post(
        user,
        post,
    )


def user_can_restore_post(user, post):
    if post.archived_at is None:
        return False

    thread = post.thread

    if (
        thread.archived_at is not None
        or thread.board.archived_at is not None
        or thread.board.category.archived_at is not None
    ):
        return False

    if user_is_forum_moderator(user):
        return True

    if (
        not user_is_forum_member(user)
        or post.author_id != user.id
        or thread.is_locked
        or thread.board.is_locked
    ):
        return False

    return user_can_access_thread(
        user,
        thread,
    )


def user_can_report_post(user, post):
    return (
        user_is_forum_member(user)
        and post.archived_at is None
        and post.author_id != user.id
        and user_can_access_thread(
            user,
            post.thread,
        )
    )


def recalculate_thread_last_post_at(thread):
    newest_post = (
        thread.posts
        .filter(
            archived_at__isnull=True,
        )
        .order_by(
            "-created_at",
            "-id",
        )
        .first()
    )

    last_post_at = (
        newest_post.created_at
        if newest_post is not None
        else None
    )

    if thread.last_post_at != last_post_at:
        thread.last_post_at = last_post_at
        thread.save(
            update_fields=[
                "last_post_at",
                "updated_at",
            ]
        )

    return last_post_at


def _replace_thread_targets(
    thread,
    target_rows,
):
    thread.targets.all().delete()

    for row in target_rows or []:
        target = ForumThreadTarget(
            thread=thread,
            **row,
        )
        target.full_clean()
        target.save()


def _create_post_attachments(
    post,
    attachments,
):
    for index, attachment in enumerate(
        attachments or []
    ):
        if isinstance(attachment, str):
            values = {
                "url": attachment,
                "label": "",
                "display_order": index,
            }
        else:
            values = {
                "url": attachment["url"],
                "label": attachment.get(
                    "label",
                    "",
                ),
                "display_order": attachment.get(
                    "display_order",
                    index,
                ),
            }

        link = ForumPostAttachment(
            post=post,
            **values,
        )
        link.full_clean()
        link.save()


def _resolve_quoted_posts(
    user,
    quoted_post_ids,
):
    post_ids = []

    for value in quoted_post_ids or []:
        try:
            post_id = int(value)
        except (
            TypeError,
            ValueError,
        ):
            continue

        if post_id not in post_ids:
            post_ids.append(post_id)

    if not post_ids:
        return []

    posts = {
        post.pk: post
        for post in (
            ForumPost.objects
            .filter(pk__in=post_ids)
            .select_related(
                "thread",
                "thread__board",
                "thread__board__category",
                "author",
            )
            .prefetch_related(
                "thread__targets",
                "thread__board__targets",
            )
        )
    }

    if len(posts) != len(post_ids):
        raise ValidationError(
            "One or more quoted posts no longer exist."
        )

    ordered_posts = [
        posts[post_id]
        for post_id in post_ids
    ]

    for post in ordered_posts:
        if (
            post.archived_at is not None
            or not user_can_access_thread(
                user,
                post.thread,
            )
        ):
            raise PermissionDenied

    return ordered_posts


def _create_post_quotes(
    post,
    quoted_posts,
):
    for quoted_post in quoted_posts:
        if quoted_post.pk == post.pk:
            continue

        ForumPostQuote.objects.get_or_create(
            post=post,
            quoted_post=quoted_post,
        )


@transaction.atomic
def create_forum_thread(
    *,
    user,
    board,
    title,
    body,
    target_rows=None,
    attachments=None,
    quoted_post_ids=None,
):
    if not user_can_create_thread(
        user,
        board,
    ):
        raise PermissionDenied

    title = title.strip()
    body = body.strip()

    if not title:
        raise ValidationError(
            "A thread title is required."
        )

    if not body:
        raise ValidationError(
            "An opening post is required."
        )

    quoted_posts = _resolve_quoted_posts(
        user,
        quoted_post_ids,
    )

    thread = ForumThread(
        board=board,
        title=title,
        created_by=user,
    )
    thread.full_clean()
    thread.save()

    _replace_thread_targets(
        thread,
        target_rows,
    )

    post = ForumPost(
        thread=thread,
        author=user,
        body=body,
    )
    post.full_clean()
    post.save()

    _create_post_attachments(
        post,
        attachments,
    )
    _create_post_quotes(
        post,
        quoted_posts,
    )

    thread.last_post_at = post.created_at
    thread.save(
        update_fields=[
            "last_post_at",
            "updated_at",
        ]
    )

    ForumThreadSubscription.objects.get_or_create(
        user=user,
        thread=thread,
    )

    mark_thread_read(
        user,
        thread,
        newest_post=post,
    )

    quoted_author_ids = {
        quoted_post.author_id
        for quoted_post in quoted_posts
        if quoted_post.author_id is not None
        and quoted_post.author_id != user.id
    }

    board_subscriber_ids = set(
        ForumBoardSubscription.objects.filter(
            board=board,
        )
        .exclude(user=user)
        .values_list(
            "user_id",
            flat=True,
        )
    )

    board_subscriber_ids -= quoted_author_ids

    board_subscribers = (
        User.objects
        .filter(
            pk__in=board_subscriber_ids,
        )
        .order_by("pk")
    )

    board_recipients = [
        recipient
        for recipient in board_subscribers
        if user_can_access_thread(
            recipient,
            thread,
        )
    ]

    if board_recipients:
        create_notifications(
            recipients=board_recipients,
            notification_type=(
                Notification.Type.COMMUNITY
            ),
            title=f"New thread: {thread.title}",
            message=(
                f"A new thread was created in "
                f"{thread.board.name}."
            ),
            source_type="ForumThread",
            source_id=thread.pk,
            target_url=reverse(
                "community:thread_detail",
                args=[thread.pk],
            ),
        )

    quote_recipients = [
        recipient
        for recipient in User.objects.filter(
            pk__in=quoted_author_ids,
        )
        if user_can_access_thread(
            recipient,
            thread,
        )
    ]

    if quote_recipients:
        create_notifications(
            recipients=quote_recipients,
            notification_type=(
                Notification.Type.COMMUNITY
            ),
            title="Your post was quoted",
            message=(
                f"Your post was quoted in "
                f'"{thread.title}".'
            ),
            source_type="ForumPost",
            source_id=post.pk,
            target_url=(
                reverse(
                    "community:thread_detail",
                    args=[thread.pk],
                )
                + f"#post-{post.pk}"
            ),
        )

    return thread


@transaction.atomic
def create_forum_post(
    *,
    user,
    thread,
    body,
    attachments=None,
    quoted_post_ids=None,
):
    if not user_can_add_post(
        user,
        thread,
    ):
        raise PermissionDenied

    body = body.strip()

    if not body:
        raise ValidationError(
            "A post body is required."
        )

    quoted_posts = _resolve_quoted_posts(
        user,
        quoted_post_ids,
    )

    post = ForumPost(
        thread=thread,
        author=user,
        body=body,
    )
    post.full_clean()
    post.save()

    _create_post_attachments(
        post,
        attachments,
    )
    _create_post_quotes(
        post,
        quoted_posts,
    )

    thread.last_post_at = post.created_at
    thread.save(
        update_fields=[
            "last_post_at",
            "updated_at",
        ]
    )

    mark_thread_read(
        user,
        thread,
        newest_post=post,
    )

    quoted_author_ids = {
        quoted_post.author_id
        for quoted_post in quoted_posts
        if quoted_post.author_id is not None
        and quoted_post.author_id != user.id
    }

    follower_ids = set(
        ForumThreadSubscription.objects.filter(
            thread=thread,
        )
        .exclude(user=user)
        .values_list(
            "user_id",
            flat=True,
        )
    )

    follower_ids -= quoted_author_ids

    followers = [
        recipient
        for recipient in User.objects.filter(
            pk__in=follower_ids,
        )
        if user_can_access_thread(
            recipient,
            thread,
        )
    ]

    target_url = (
        reverse(
            "community:thread_detail",
            args=[thread.pk],
        )
        + f"#post-{post.pk}"
    )

    if followers:
        create_notifications(
            recipients=followers,
            notification_type=(
                Notification.Type.COMMUNITY
            ),
            title=f"New reply: {thread.title}",
            message=(
                "A new post was added to a "
                "thread you follow."
            ),
            source_type="ForumPost",
            source_id=post.pk,
            target_url=target_url,
        )

    quote_recipients = [
        recipient
        for recipient in User.objects.filter(
            pk__in=quoted_author_ids,
        )
        if user_can_access_thread(
            recipient,
            thread,
        )
    ]

    if quote_recipients:
        create_notifications(
            recipients=quote_recipients,
            notification_type=(
                Notification.Type.COMMUNITY
            ),
            title="Your post was quoted",
            message=(
                f'Your post was quoted in '
                f'"{thread.title}".'
            ),
            source_type="ForumPost",
            source_id=post.pk,
            target_url=target_url,
        )

    return post


@transaction.atomic
def edit_forum_thread(
    *,
    user,
    thread,
    title,
    target_rows,
):
    if not user_can_change_thread(
        user,
        thread,
    ):
        raise PermissionDenied

    title = title.strip()

    if not title:
        raise ValidationError(
            "A thread title is required."
        )

    thread.title = title
    thread.full_clean()
    thread.save(
        update_fields=[
            "title",
            "updated_at",
        ]
    )

    _replace_thread_targets(
        thread,
        target_rows,
    )

    return thread


@transaction.atomic
def edit_forum_post(
    *,
    user,
    post,
    body,
):
    if not user_can_edit_post(
        user,
        post,
    ):
        raise PermissionDenied

    body = body.strip()

    if not body:
        raise ValidationError(
            "A post body is required."
        )

    post.body = body
    post.edited_at = timezone.now()
    post.edited_by = user
    post.full_clean()

    post.save(
        update_fields=[
            "body",
            "edited_at",
            "edited_by",
        ]
    )

    return post


@transaction.atomic
def archive_forum_category(
    *,
    user,
    category,
):
    if not user_can_manage_forum_categories(
        user
    ):
        raise PermissionDenied

    if category.archived_at is None:
        category.archived_at = timezone.now()
        category.archived_by = user
        category.save(
            update_fields=[
                "archived_at",
                "archived_by",
                "updated_at",
            ]
        )

    return category


@transaction.atomic
def restore_forum_category(
    *,
    user,
    category,
):
    if not user_can_manage_forum_categories(
        user
    ):
        raise PermissionDenied

    if category.archived_at is not None:
        category.archived_at = None
        category.archived_by = None
        category.save(
            update_fields=[
                "archived_at",
                "archived_by",
                "updated_at",
            ]
        )

    return category


@transaction.atomic
def archive_forum_board(
    *,
    user,
    board,
):
    if not user_can_manage_forum_boards(
        user
    ):
        raise PermissionDenied

    if board.archived_at is None:
        board.archived_at = timezone.now()
        board.archived_by = user
        board.save(
            update_fields=[
                "archived_at",
                "archived_by",
                "updated_at",
            ]
        )

    return board


@transaction.atomic
def restore_forum_board(
    *,
    user,
    board,
):
    if not user_can_manage_forum_boards(
        user
    ):
        raise PermissionDenied

    if board.archived_at is not None:
        board.archived_at = None
        board.archived_by = None
        board.save(
            update_fields=[
                "archived_at",
                "archived_by",
                "updated_at",
            ]
        )

    return board


@transaction.atomic
def archive_forum_thread(
    *,
    user,
    thread,
):
    if not user_can_archive_thread(
        user,
        thread,
    ):
        raise PermissionDenied

    thread.archived_at = timezone.now()
    thread.archived_by = user

    thread.save(
        update_fields=[
            "archived_at",
            "archived_by",
            "updated_at",
        ]
    )

    return thread


@transaction.atomic
def restore_forum_thread(
    *,
    user,
    thread,
):
    if not user_can_restore_thread(
        user,
        thread,
    ):
        raise PermissionDenied

    thread.archived_at = None
    thread.archived_by = None

    thread.save(
        update_fields=[
            "archived_at",
            "archived_by",
            "updated_at",
        ]
    )

    return thread


@transaction.atomic
def archive_forum_post(
    *,
    user,
    post,
):
    if not user_can_archive_post(
        user,
        post,
    ):
        raise PermissionDenied

    post.archived_at = timezone.now()
    post.archived_by = user

    post.save(
        update_fields=[
            "archived_at",
            "archived_by",
        ]
    )

    recalculate_thread_last_post_at(
        post.thread
    )

    return post


@transaction.atomic
def restore_forum_post(
    *,
    user,
    post,
):
    if not user_can_restore_post(
        user,
        post,
    ):
        raise PermissionDenied

    post.archived_at = None
    post.archived_by = None

    post.save(
        update_fields=[
            "archived_at",
            "archived_by",
        ]
    )

    recalculate_thread_last_post_at(
        post.thread
    )

    return post


@transaction.atomic
def set_board_locked(
    *,
    user,
    board,
    locked,
):
    if not user_can_manage_forum_boards(
        user
    ):
        raise PermissionDenied

    board.is_locked = locked
    board.locked_at = (
        timezone.now()
        if locked
        else None
    )
    board.locked_by = (
        user
        if locked
        else None
    )

    board.save(
        update_fields=[
            "is_locked",
            "locked_at",
            "locked_by",
            "updated_at",
        ]
    )

    return board


@transaction.atomic
def set_thread_pinned(
    *,
    user,
    thread,
    pinned,
):
    if not user_is_forum_moderator(
        user
    ):
        raise PermissionDenied

    thread.is_pinned = pinned
    thread.pinned_at = (
        timezone.now()
        if pinned
        else None
    )
    thread.pinned_by = (
        user
        if pinned
        else None
    )

    thread.save(
        update_fields=[
            "is_pinned",
            "pinned_at",
            "pinned_by",
            "updated_at",
        ]
    )

    return thread


@transaction.atomic
def set_thread_locked(
    *,
    user,
    thread,
    locked,
):
    if not user_is_forum_moderator(
        user
    ):
        raise PermissionDenied

    thread.is_locked = locked
    thread.locked_at = (
        timezone.now()
        if locked
        else None
    )
    thread.locked_by = (
        user
        if locked
        else None
    )

    thread.save(
        update_fields=[
            "is_locked",
            "locked_at",
            "locked_by",
            "updated_at",
        ]
    )

    return thread


@transaction.atomic
def move_forum_thread(
    *,
    user,
    thread,
    destination_board,
):
    if not user_is_forum_moderator(
        user
    ):
        raise PermissionDenied

    if thread.board_id == destination_board.pk:
        raise ValidationError(
            "The thread is already in that board."
        )

    if (
        destination_board.archived_at is not None
        or destination_board.category.archived_at
        is not None
    ):
        raise ValidationError(
            "A thread cannot be moved into "
            "an archived board."
        )

    thread.board = destination_board
    thread.full_clean()

    thread.save(
        update_fields=[
            "board",
            "updated_at",
        ]
    )

    return thread


@transaction.atomic
def move_forum_posts(
    *,
    user,
    posts,
    destination_thread,
):
    if not user_is_forum_moderator(
        user
    ):
        raise PermissionDenied

    posts = list(posts)

    if not posts:
        raise ValidationError(
            "Select at least one post."
        )

    source_thread_ids = {
        post.thread_id
        for post in posts
    }

    if len(source_thread_ids) != 1:
        raise ValidationError(
            "Selected posts must come "
            "from one thread."
        )

    source_thread = posts[0].thread

    if source_thread.pk == destination_thread.pk:
        raise ValidationError(
            "The destination thread must "
            "be different from the source thread."
        )

    if (
        destination_thread.archived_at is not None
        or destination_thread.board.archived_at
        is not None
        or destination_thread.board.category.archived_at
        is not None
    ):
        raise ValidationError(
            "Posts cannot be moved into "
            "an archived thread."
        )

    ForumPost.objects.filter(
        pk__in=[
            post.pk
            for post in posts
        ]
    ).update(
        thread=destination_thread,
    )

    recalculate_thread_last_post_at(
        source_thread
    )
    recalculate_thread_last_post_at(
        destination_thread
    )

    return destination_thread


@transaction.atomic
def split_forum_thread(
    *,
    user,
    source_thread,
    posts,
    destination_board,
    title,
):
    if not user_is_forum_moderator(
        user
    ):
        raise PermissionDenied

    posts = list(posts)

    if not posts:
        raise ValidationError(
            "Select at least one post."
        )

    if any(
        post.thread_id != source_thread.pk
        for post in posts
    ):
        raise ValidationError(
            "Every selected post must belong "
            "to the source thread."
        )

    if (
        destination_board.archived_at is not None
        or destination_board.category.archived_at
        is not None
    ):
        raise ValidationError(
            "A split thread cannot be created "
            "in an archived board."
        )

    title = title.strip()

    if not title:
        raise ValidationError(
            "A thread title is required."
        )

    new_thread = ForumThread(
        board=destination_board,
        title=title,
        created_by=source_thread.created_by,
    )
    new_thread.full_clean()
    new_thread.save()

    _replace_thread_targets(
        new_thread,
        [
            {
                f"{field_name}_id": getattr(
                    target,
                    f"{field_name}_id",
                )
                for field_name in (
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
            }
            for target
            in source_thread.targets.all()
        ],
    )

    ForumPost.objects.filter(
        pk__in=[
            post.pk
            for post in posts
        ]
    ).update(
        thread=new_thread,
    )

    recalculate_thread_last_post_at(
        source_thread
    )
    recalculate_thread_last_post_at(
        new_thread
    )

    return new_thread


@transaction.atomic
def merge_forum_threads(
    *,
    user,
    source_thread,
    destination_thread,
):
    if not user_is_forum_moderator(
        user
    ):
        raise PermissionDenied

    if source_thread.pk == destination_thread.pk:
        raise ValidationError(
            "A thread cannot be merged into itself."
        )

    if source_thread.merged_into_id is not None:
        raise ValidationError(
            "The source thread was already merged."
        )

    if source_thread.archived_at is not None:
        raise ValidationError(
            "An archived thread cannot be merged."
        )

    if (
        destination_thread.merged_into_id is not None
        or destination_thread.archived_at is not None
        or destination_thread.board.archived_at
        is not None
        or destination_thread.board.category.archived_at
        is not None
    ):
        raise ValidationError(
            "The destination thread must be active."
        )

    ForumPost.objects.filter(
        thread=source_thread,
    ).update(
        thread=destination_thread,
    )

    source_thread.archived_at = timezone.now()
    source_thread.archived_by = user
    source_thread.merged_into = destination_thread

    source_thread.full_clean()
    source_thread.save(
        update_fields=[
            "archived_at",
            "archived_by",
            "merged_into",
            "updated_at",
        ]
    )

    recalculate_thread_last_post_at(
        source_thread
    )
    recalculate_thread_last_post_at(
        destination_thread
    )

    return destination_thread


def thread_is_unread(user, thread):
    if thread.last_post_at is None:
        return False

    read_state = (
        ForumThreadReadState.objects
        .filter(
            user=user,
            thread=thread,
        )
        .first()
    )

    if read_state is None:
        return True

    return (
        thread.last_post_at
        > read_state.last_read_at
    )


def get_first_unread_post(user, thread):
    posts = thread.posts.filter(
        archived_at__isnull=True,
    )

    read_state = (
        ForumThreadReadState.objects
        .filter(
            user=user,
            thread=thread,
        )
        .first()
    )

    if read_state is not None:
        posts = posts.filter(
            created_at__gt=read_state.last_read_at,
        )

    return posts.order_by(
        "created_at",
        "id",
    ).first()


def mark_thread_read(
    user,
    thread,
    *,
    newest_post=None,
):
    if not user_can_access_thread(
        user,
        thread,
    ):
        raise PermissionDenied

    if newest_post is None:
        newest_post = (
            thread.posts
            .filter(
                archived_at__isnull=True,
            )
            .order_by(
                "-created_at",
                "-id",
            )
            .first()
        )

    if newest_post is None:
        return None

    if (
        newest_post.thread_id != thread.pk
        or newest_post.archived_at is not None
    ):
        raise ValidationError(
            "The read marker must reference "
            "an active post in this thread."
        )

    read_state, _ = (
        ForumThreadReadState.objects
        .update_or_create(
            user=user,
            thread=thread,
            defaults={
                "last_read_at":
                    newest_post.created_at,
            },
        )
    )

    return read_state


def board_has_unread_threads(user, board):
    return any(
        thread_is_unread(
            user,
            thread,
        )
        for thread
        in get_accessible_threads(
            user,
            board=board,
        )
    )


def category_has_unread_threads(
    user,
    category,
):
    return any(
        board_has_unread_threads(
            user,
            board,
        )
        for board
        in get_accessible_boards(
            user
        ).filter(
            category=category,
        )
    )


def subscribe_to_thread(user, thread):
    if (
        not user_is_forum_member(user)
        or not user_can_access_thread(
            user,
            thread,
        )
    ):
        raise PermissionDenied

    subscription, _ = (
        ForumThreadSubscription.objects
        .get_or_create(
            user=user,
            thread=thread,
        )
    )

    return subscription


def unsubscribe_from_thread(user, thread):
    ForumThreadSubscription.objects.filter(
        user=user,
        thread=thread,
    ).delete()


def subscribe_to_board(user, board):
    if (
        not user_is_forum_member(user)
        or not user_can_access_board(
            user,
            board,
        )
    ):
        raise PermissionDenied

    subscription, _ = (
        ForumBoardSubscription.objects
        .get_or_create(
            user=user,
            board=board,
        )
    )

    return subscription


def unsubscribe_from_board(user, board):
    ForumBoardSubscription.objects.filter(
        user=user,
        board=board,
    ).delete()


@transaction.atomic
def create_post_report(
    *,
    user,
    post,
    reason,
):
    if not user_can_report_post(
        user,
        post,
    ):
        raise PermissionDenied

    reason = reason.strip()

    if not reason:
        raise ValidationError(
            "A report reason is required."
        )

    if ForumPostReport.objects.filter(
        post=post,
        reporter=user,
        status=ForumPostReport.Status.OPEN,
    ).exists():
        raise ValidationError(
            "You already have an open "
            "report for this post."
        )

    report = ForumPostReport(
        post=post,
        reporter=user,
        reason=reason,
    )

    report.full_clean()
    report.save()

    return report


@transaction.atomic
def resolve_post_report(
    *,
    user,
    report,
    status,
    resolution_note="",
):
    if not user_is_forum_moderator(
        user
    ):
        raise PermissionDenied

    if status not in {
        ForumPostReport.Status.RESOLVED,
        ForumPostReport.Status.DISMISSED,
    }:
        raise ValidationError(
            "A report may only be "
            "resolved or dismissed."
        )

    report.status = status
    report.reviewed_at = timezone.now()
    report.reviewed_by = user
    report.resolution_note = (
        resolution_note.strip()
    )

    report.full_clean()
    report.save(
        update_fields=[
            "status",
            "reviewed_at",
            "reviewed_by",
            "resolution_note",
        ]
    )

    if (
        report.reporter is not None
        and report.reporter_id != user.id
        and user_can_access_thread(
            report.reporter,
            report.post.thread,
        )
    ):
        create_notifications(
            recipients=[
                report.reporter,
            ],
            notification_type=(
                Notification.Type.COMMUNITY
            ),
            title="Forum report reviewed",
            message=(
                "A report you submitted "
                f"was {status.lower()}."
            ),
            source_type="ForumPostReport",
            source_id=report.pk,
            target_url=(
                reverse(
                    "community:thread_detail",
                    args=[
                        report.post.thread_id,
                    ],
                )
                + f"#post-{report.post_id}"
            ),
        )

    return report


def search_forum(user, query):
    query = query.strip()

    if not query:
        return {
            "threads":
                ForumThread.objects.none(),
            "posts":
                ForumPost.objects.none(),
        }

    thread_ids = list(
        get_accessible_threads(user)
        .values_list(
            "id",
            flat=True,
        )
    )

    matching_posts = (
        ForumPost.objects
        .filter(
            thread_id__in=thread_ids,
            archived_at__isnull=True,
        )
        .filter(
            Q(body__icontains=query)
            | Q(
                author__username__icontains=query
            )
            | Q(
                author__display_name__icontains=query
            )
        )
        .select_related(
            "thread",
            "thread__board",
            "thread__board__category",
            "author",
        )
        .order_by(
            "-created_at",
            "-id",
        )
    )

    matching_threads = (
        ForumThread.objects
        .filter(
            id__in=thread_ids,
        )
        .filter(
            Q(title__icontains=query)
            | Q(
                created_by__username__icontains=query
            )
            | Q(
                created_by__display_name__icontains=query
            )
            | Q(
                posts__body__icontains=query,
                posts__archived_at__isnull=True,
            )
            | Q(
                posts__author__username__icontains=query,
                posts__archived_at__isnull=True,
            )
            | Q(
                posts__author__display_name__icontains=query,
                posts__archived_at__isnull=True,
            )
        )
        .select_related(
            "board",
            "board__category",
            "created_by",
        )
        .distinct()
        .order_by(
            "-is_pinned",
            F("last_post_at").desc(
                nulls_last=True,
            ),
            "-created_at",
        )
    )

    return {
        "threads": matching_threads,
        "posts": matching_posts,
    }


@transaction.atomic
def save_thread_draft(
    *,
    user,
    board,
    title="",
    body="",
    target_data=None,
    attachment_links=None,
    quoted_post_ids=None,
    draft=None,
):
    if (
        not user_is_forum_member(user)
        or not user_can_access_board(
            user,
            board,
        )
    ):
        raise PermissionDenied

    if draft is None:
        draft = ForumDraft(
            user=user,
            draft_type=(
                ForumDraft.DraftType.THREAD
            ),
            board=board,
        )

    elif (
        draft.user_id != user.id
        or draft.draft_type
        != ForumDraft.DraftType.THREAD
        or draft.board_id != board.pk
    ):
        raise PermissionDenied

    draft.title = title
    draft.body = body
    draft.target_data = target_data or []
    draft.attachment_links = (
        attachment_links or []
    )
    draft.quoted_post_ids = (
        quoted_post_ids or []
    )

    draft.full_clean()
    draft.save()

    return draft


@transaction.atomic
def save_post_draft(
    *,
    user,
    thread,
    body="",
    attachment_links=None,
    quoted_post_ids=None,
    draft=None,
):
    if (
        not user_is_forum_member(user)
        or not user_can_access_thread(
            user,
            thread,
        )
    ):
        raise PermissionDenied

    if draft is None:
        draft = ForumDraft(
            user=user,
            draft_type=(
                ForumDraft.DraftType.POST
            ),
            thread=thread,
        )

    elif (
        draft.user_id != user.id
        or draft.draft_type
        != ForumDraft.DraftType.POST
        or draft.thread_id != thread.pk
    ):
        raise PermissionDenied

    draft.title = ""
    draft.body = body
    draft.target_data = []
    draft.attachment_links = (
        attachment_links or []
    )
    draft.quoted_post_ids = (
        quoted_post_ids or []
    )

    draft.full_clean()
    draft.save()

    return draft


@transaction.atomic
def publish_forum_draft(
    *,
    user,
    draft,
):
    if draft.user_id != user.id:
        raise PermissionDenied

    if (
        draft.draft_type
        == ForumDraft.DraftType.THREAD
    ):
        result = create_forum_thread(
            user=user,
            board=draft.board,
            title=draft.title,
            body=draft.body,
            target_rows=draft.target_data,
            attachments=draft.attachment_links,
            quoted_post_ids=draft.quoted_post_ids,
        )

    else:
        result = create_forum_post(
            user=user,
            thread=draft.thread,
            body=draft.body,
            attachments=draft.attachment_links,
            quoted_post_ids=draft.quoted_post_ids,
        )

    draft.delete()

    return result