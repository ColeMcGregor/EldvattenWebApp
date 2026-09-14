from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import (
    PermissionDenied,
    ValidationError,
)
from django.db import transaction
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.urls import reverse
from django.views.decorators.http import require_POST

from accounts.needs_attention import (
    get_needs_attention_items,
)
from audit.models import AuditLog
from audit.services import record_audit_event

from .forms import (
    FORUM_TARGET_FIELDS,
    ForumBoardForm,
    ForumBoardTargetFormSet,
    ForumBoardThreadCreationTargetFormSet,
    ForumCategoryForm,
    ForumDraftContentForm,
    ForumPostAttachmentFormSet,
    ForumPostForm,
    ForumPostMoveForm,
    ForumPostReportForm,
    ForumThreadCreateForm,
    ForumThreadEditForm,
    ForumThreadMergeForm,
    ForumThreadMoveForm,
    ForumThreadSplitForm,
    ForumThreadTargetFormSet,
)
from .models import (
    ForumBoard,
    ForumBoardSubscription,
    ForumCategory,
    ForumDraft,
    ForumPost,
    ForumPostReport,
    ForumThread,
    ForumThreadSubscription,
)
from .services import (
    archive_forum_board,
    archive_forum_category,
    archive_forum_post,
    archive_forum_thread,
    board_has_unread_threads,
    category_has_unread_threads,
    create_forum_post,
    create_forum_thread,
    create_post_report,
    edit_forum_post,
    edit_forum_thread,
    get_accessible_boards,
    get_accessible_categories,
    get_accessible_threads,
    get_first_unread_post,
    mark_thread_read,
    merge_forum_threads,
    move_forum_posts,
    move_forum_thread,
    publish_forum_draft,
    restore_forum_board,
    restore_forum_category,
    restore_forum_post,
    restore_forum_thread,
    save_post_draft,
    save_thread_draft,
    search_forum,
    set_board_locked,
    set_thread_locked,
    set_thread_pinned,
    split_forum_thread,
    subscribe_to_board,
    subscribe_to_thread,
    thread_is_unread,
    unsubscribe_from_board,
    unsubscribe_from_thread,
    user_can_access_board,
    user_can_access_thread,
    user_can_add_post,
    user_can_archive_post,
    user_can_archive_thread,
    user_can_change_thread,
    user_can_create_thread,
    user_can_edit_post,
    user_can_manage_forum_boards,
    user_can_manage_forum_categories,
    user_can_read_forum,
    user_can_report_post,
    user_can_restore_post,
    user_can_restore_thread,
    user_can_view_archived_forum,
    user_is_forum_member,
    user_is_forum_moderator,
)


def _validation_message(error):
    if hasattr(error, "messages"):
        return " ".join(error.messages)

    return str(error)


def _target_rows(formset, *, json_safe=False):
    rows = []

    for form in formset.forms:
        if not hasattr(
            form,
            "cleaned_data",
        ):
            continue

        if form.cleaned_data.get("DELETE"):
            continue

        row = {
            field_name:
                form.cleaned_data.get(
                    field_name
                )
            for field_name
            in FORUM_TARGET_FIELDS
        }

        if not any(
            value is not None
            for value in row.values()
        ):
            continue

        if json_safe:
            row = {
                f"{field_name}_id": (
                    value.pk
                    if value is not None
                    else None
                )
                for field_name, value
                in row.items()
            }

        rows.append(row)

    return rows


def _attachment_rows(formset):
    attachments = []

    for form in formset.forms:
        if not hasattr(
            form,
            "cleaned_data",
        ):
            continue

        if form.cleaned_data.get("DELETE"):
            continue

        url = form.cleaned_data.get("url")

        if not url:
            continue

        attachments.append(
            {
                "label":
                    form.cleaned_data.get(
                        "label",
                        "",
                    ),
                "url": url,
                "display_order":
                    form.cleaned_data.get(
                        "display_order",
                        0,
                    ),
            }
        )

    return attachments


def _audit_values(obj):
    values = {}

    for field in obj._meta.fields:
        if field.name in {
            "id",
            "created_at",
            "updated_at",
        }:
            continue

        if field.is_relation:
            values[field.name] = getattr(
                obj,
                f"{field.name}_id",
            )
            continue

        value = getattr(
            obj,
            field.name,
        )

        values[field.name] = (
            value.isoformat()
            if hasattr(value, "isoformat")
            else value
        )

    if isinstance(
        obj,
        ForumBoard,
    ):
        values["targets"] = [
            {
                field_name: getattr(
                    target,
                    f"{field_name}_id",
                )
                for field_name
                in FORUM_TARGET_FIELDS
            }
            for target
            in obj.targets.all().order_by("id")
        ]

        values[
            "thread_creation_targets"
        ] = [
            {
                field_name: getattr(
                    target,
                    f"{field_name}_id",
                )
                for field_name
                in FORUM_TARGET_FIELDS
            }
            for target
            in obj.thread_creation_targets
            .all()
            .order_by("id")
        ]

    elif isinstance(
        obj,
        ForumThread,
    ):
        values["targets"] = [
            {
                field_name: getattr(
                    target,
                    f"{field_name}_id",
                )
                for field_name
                in FORUM_TARGET_FIELDS
            }
            for target
            in obj.targets.all().order_by("id")
        ]

    elif isinstance(
        obj,
        ForumPost,
    ):
        values["attachments"] = list(
            obj.attachments
            .order_by(
                "display_order",
                "id",
            )
            .values(
                "label",
                "url",
                "display_order",
            )
        )

        values["quoted_post_ids"] = list(
            obj.quotes
            .order_by("id")
            .values_list(
                "quoted_post_id",
                flat=True,
            )
        )

    return values


def _audit(
    request,
    obj,
    *,
    action,
    old_value=None,
    notes="",
):
    record_audit_event(
        actor=request.user,
        request=request,
        action=action,
        target_type=obj._meta.verbose_name,
        target_id=obj.pk,
        target_label=str(obj),
        old_value=old_value,
        new_value=(
            None
            if action == AuditLog.Action.DELETE
            else _audit_values(obj)
        ),
        source=AuditLog.Source.WEB_APP,
        method=AuditLog.Method.MANUAL,
        notes=notes,
    )


@login_required
def forum_index(request):
    if not user_can_read_forum(
        request.user
    ) and not user_is_forum_moderator(
        request.user
    ):
        raise PermissionDenied

    show_archived = (
        request.GET.get("archived") == "1"
        and user_can_view_archived_forum(
            request.user
        )
    )

    categories = list(
        get_accessible_categories(
            request.user,
            include_archived=show_archived,
        )
    )

    boards = list(
        get_accessible_boards(
            request.user,
            include_archived=show_archived,
        )
    )

    boards_by_category = {}

    for board in boards:
        board.has_unread = (
            board_has_unread_threads(
                request.user,
                board,
            )
            if board.archived_at is None
            and board.category.archived_at
            is None
            else False
        )

        boards_by_category.setdefault(
            board.category_id,
            [],
        ).append(board)

    category_sections = []

    for category in categories:
        category.has_unread = (
            category_has_unread_threads(
                request.user,
                category,
            )
            if category.archived_at is None
            else False
        )

        category_sections.append(
            {
                "category": category,
                "boards":
                    boards_by_category.get(
                        category.pk,
                        [],
                    ),
            }
        )

    return render(
        request,
        "community/forum/index.html",
        {
            "category_sections":
                category_sections,
            "show_archived":
                show_archived,
            "can_view_archived":
                user_can_view_archived_forum(
                    request.user
                ),
            "can_manage_categories":
                user_can_manage_forum_categories(
                    request.user
                ),
            "can_manage_boards":
                user_can_manage_forum_boards(
                    request.user
                ),
            "needs_attention_items":
                get_needs_attention_items(
                    request.user
                ),
        },
    )


@login_required
def forum_search(request):
    if not user_can_read_forum(
        request.user
    ) and not user_is_forum_moderator(
        request.user
    ):
        raise PermissionDenied

    query = request.GET.get(
        "q",
        "",
    )

    results = search_forum(
        request.user,
        query,
    )

    return render(
        request,
        "community/forum/search.html",
        {
            "query": query,
            "threads": results["threads"],
            "posts": results["posts"],
        },
    )


@login_required
def category_create(request):
    if not user_can_manage_forum_categories(
        request.user
    ):
        raise PermissionDenied

    if request.method == "POST":
        form = ForumCategoryForm(
            request.POST
        )

        if form.is_valid():
            category = form.save()

            _audit(
                request,
                category,
                action=AuditLog.Action.CREATE,
            )

            return redirect(
                "community:forum_index"
            )

    else:
        form = ForumCategoryForm()

    return render(
        request,
        "community/forum/category_form.html",
        {
            "form": form,
            "page_title":
                "Create Category",
        },
    )


@login_required
def category_edit(
    request,
    category_id,
):
    if not user_can_manage_forum_categories(
        request.user
    ):
        raise PermissionDenied

    category = get_object_or_404(
        ForumCategory,
        pk=category_id,
    )

    if request.method == "POST":
        old_value = _audit_values(
            category
        )

        form = ForumCategoryForm(
            request.POST,
            instance=category,
        )

        if form.is_valid():
            category = form.save()

            _audit(
                request,
                category,
                action=AuditLog.Action.UPDATE,
                old_value=old_value,
            )

            return redirect(
                "community:forum_index"
            )

    else:
        form = ForumCategoryForm(
            instance=category
        )

    return render(
        request,
        "community/forum/category_form.html",
        {
            "form": form,
            "category": category,
            "page_title":
                "Edit Category",
        },
    )


@login_required
@require_POST
def category_archive(
    request,
    category_id,
):
    category = get_object_or_404(
        ForumCategory,
        pk=category_id,
    )

    old_value = _audit_values(
        category
    )

    category = archive_forum_category(
        user=request.user,
        category=category,
    )

    _audit(
        request,
        category,
        action=AuditLog.Action.UPDATE,
        old_value=old_value,
        notes="Forum category archived.",
    )

    return redirect(
        "community:forum_index"
    )


@login_required
@require_POST
def category_restore(
    request,
    category_id,
):
    category = get_object_or_404(
        ForumCategory,
        pk=category_id,
    )

    old_value = _audit_values(
        category
    )

    category = restore_forum_category(
        user=request.user,
        category=category,
    )

    _audit(
        request,
        category,
        action=AuditLog.Action.UPDATE,
        old_value=old_value,
        notes="Forum category restored.",
    )

    return redirect(
        "community:forum_index"
    )


@login_required
def board_create(
    request,
    category_id,
):
    if not user_can_manage_forum_boards(
        request.user
    ):
        raise PermissionDenied

    category = get_object_or_404(
        ForumCategory,
        pk=category_id,
    )

    board = ForumBoard(
        category=category,
    )

    form = ForumBoardForm(
        request.POST or None,
        instance=board,
    )
    form.fields["category"].disabled = True

    target_formset = (
        ForumBoardTargetFormSet(
            request.POST or None,
            instance=board,
            prefix="targets",
        )
    )

    creation_target_formset = (
        ForumBoardThreadCreationTargetFormSet(
            request.POST or None,
            instance=board,
            prefix="creation_targets",
        )
    )

    if request.method == "POST" and form.is_valid():
        board = form.save(
            commit=False
        )
        board.category = category

        if (
            target_formset.is_valid()
            and creation_target_formset
            .is_valid()
        ):
            with transaction.atomic():
                board.save()

                target_formset.instance = (
                    board
                )
                target_formset.save()

                if (
                    board.thread_creation_policy
                    == ForumBoard
                    .ThreadCreationPolicy
                    .TARGETED
                ):
                    creation_target_formset.instance = board
                    creation_target_formset.save()

                else:
                    board.thread_creation_targets.all().delete()

            _audit(
                request,
                board,
                action=AuditLog.Action.CREATE,
            )

            return redirect(
                "community:board_detail",
                board_id=board.pk,
            )

    return render(
        request,
        "community/forum/board_form.html",
        {
            "form": form,
            "target_formset":
                target_formset,
            "creation_target_formset":
                creation_target_formset,
            "category": category,
            "page_title":
                "Create Board",
        },
    )


@login_required
def board_detail(
    request,
    board_id,
):
    board = get_object_or_404(
        ForumBoard.objects
        .select_related("category")
        .prefetch_related(
            "targets",
            "thread_creation_targets",
        ),
        pk=board_id,
    )

    show_archived = (
        request.GET.get("archived") == "1"
        and user_can_view_archived_forum(
            request.user
        )
    )

    if not user_can_access_board(
        request.user,
        board,
        include_archived=show_archived,
    ):
        raise PermissionDenied

    threads = list(
        get_accessible_threads(
            request.user,
            board=board,
            include_archived=show_archived,
        )
    )

    for thread in threads:
        thread.is_unread_for_user = (
            thread_is_unread(
                request.user,
                thread,
            )
            if thread.archived_at is None
            else False
        )

    return render(
        request,
        "community/forum/board_detail.html",
        {
            "board": board,
            "threads": threads,
            "show_archived":
                show_archived,
            "can_view_archived":
                user_can_view_archived_forum(
                    request.user
                ),
            "is_subscribed":
                ForumBoardSubscription
                .objects
                .filter(
                    user=request.user,
                    board=board,
                )
                .exists(),
            "can_create_thread":
                user_can_create_thread(
                    request.user,
                    board,
                ),
            "can_manage_board":
                user_can_manage_forum_boards(
                    request.user
                ),
            "can_moderate":
                user_is_forum_moderator(
                    request.user
                ),
            "needs_attention_items":
                get_needs_attention_items(
                    request.user
                ),
        },
    )


@login_required
def board_edit(
    request,
    board_id,
):
    if not user_can_manage_forum_boards(
        request.user
    ):
        raise PermissionDenied

    board = get_object_or_404(
        ForumBoard.objects
        .select_related("category")
        .prefetch_related(
            "targets",
            "thread_creation_targets",
        ),
        pk=board_id,
    )

    old_value = _audit_values(
        board
    )

    form = ForumBoardForm(
        request.POST or None,
        instance=board,
    )

    target_formset = (
        ForumBoardTargetFormSet(
            request.POST or None,
            instance=board,
            prefix="targets",
        )
    )

    creation_target_formset = (
        ForumBoardThreadCreationTargetFormSet(
            request.POST or None,
            instance=board,
            prefix="creation_targets",
        )
    )

    if (
        request.method == "POST"
        and form.is_valid()
        and target_formset.is_valid()
        and creation_target_formset.is_valid()
    ):
        with transaction.atomic():
            board = form.save()

            target_formset.instance = board
            target_formset.save()

            if (
                board.thread_creation_policy
                == ForumBoard
                .ThreadCreationPolicy
                .TARGETED
            ):
                creation_target_formset.instance = board
                creation_target_formset.save()

            else:
                board.thread_creation_targets.all().delete()

        _audit(
            request,
            board,
            action=AuditLog.Action.UPDATE,
            old_value=old_value,
        )

        return redirect(
            "community:board_detail",
            board_id=board.pk,
        )

    return render(
        request,
        "community/forum/board_form.html",
        {
            "form": form,
            "target_formset":
                target_formset,
            "creation_target_formset":
                creation_target_formset,
            "board": board,
            "page_title":
                "Edit Board",
        },
    )


@login_required
@require_POST
def board_archive(
    request,
    board_id,
):
    board = get_object_or_404(
        ForumBoard.objects
        .select_related("category"),
        pk=board_id,
    )

    old_value = _audit_values(
        board
    )

    board = archive_forum_board(
        user=request.user,
        board=board,
    )

    _audit(
        request,
        board,
        action=AuditLog.Action.UPDATE,
        old_value=old_value,
        notes="Forum board archived.",
    )

    return redirect(
        "community:forum_index"
    )


@login_required
@require_POST
def board_restore(
    request,
    board_id,
):
    board = get_object_or_404(
        ForumBoard.objects
        .select_related("category"),
        pk=board_id,
    )

    old_value = _audit_values(
        board
    )

    board = restore_forum_board(
        user=request.user,
        board=board,
    )

    _audit(
        request,
        board,
        action=AuditLog.Action.UPDATE,
        old_value=old_value,
        notes="Forum board restored.",
    )

    return redirect(
        "community:board_detail",
        board_id=board.pk,
    )


@login_required
@require_POST
def board_lock(
    request,
    board_id,
):
    board = get_object_or_404(
        ForumBoard.objects
        .select_related("category"),
        pk=board_id,
    )

    old_value = _audit_values(
        board
    )

    board = set_board_locked(
        user=request.user,
        board=board,
        locked=True,
    )

    _audit(
        request,
        board,
        action=AuditLog.Action.UPDATE,
        old_value=old_value,
        notes="Forum board locked.",
    )

    return redirect(
        "community:board_detail",
        board_id=board.pk,
    )


@login_required
@require_POST
def board_unlock(
    request,
    board_id,
):
    board = get_object_or_404(
        ForumBoard.objects
        .select_related("category"),
        pk=board_id,
    )

    old_value = _audit_values(
        board
    )

    board = set_board_locked(
        user=request.user,
        board=board,
        locked=False,
    )

    _audit(
        request,
        board,
        action=AuditLog.Action.UPDATE,
        old_value=old_value,
        notes="Forum board unlocked.",
    )

    return redirect(
        "community:board_detail",
        board_id=board.pk,
    )


@login_required
@require_POST
def board_subscribe(
    request,
    board_id,
):
    board = get_object_or_404(
        ForumBoard.objects
        .select_related("category")
        .prefetch_related("targets"),
        pk=board_id,
    )

    subscribe_to_board(
        request.user,
        board,
    )

    return redirect(
        "community:board_detail",
        board_id=board.pk,
    )


@login_required
@require_POST
def board_unsubscribe(
    request,
    board_id,
):
    board = get_object_or_404(
        ForumBoard,
        pk=board_id,
    )

    unsubscribe_from_board(
        request.user,
        board,
    )

    return redirect(
        "community:board_detail",
        board_id=board.pk,
    )


@login_required
def thread_create(
    request,
    board_id,
):
    board = get_object_or_404(
        ForumBoard.objects
        .select_related("category")
        .prefetch_related(
            "targets",
            "thread_creation_targets",
        ),
        pk=board_id,
    )

    if not user_can_create_thread(
        request.user,
        board,
    ):
        raise PermissionDenied

    thread_shell = ForumThread(
        board=board,
        created_by=request.user,
    )

    post_shell = ForumPost(
        author=request.user,
    )

    form = ForumThreadCreateForm(
        request.POST or None
    )

    target_formset = (
        ForumThreadTargetFormSet(
            request.POST or None,
            instance=thread_shell,
            prefix="targets",
        )
    )

    attachment_formset = (
        ForumPostAttachmentFormSet(
            request.POST or None,
            instance=post_shell,
            prefix="attachments",
        )
    )

    if (
        request.method == "POST"
        and form.is_valid()
        and target_formset.is_valid()
        and attachment_formset.is_valid()
    ):
        try:
            thread = create_forum_thread(
                user=request.user,
                board=board,
                title=form.cleaned_data["title"],
                body=form.cleaned_data["body"],
                target_rows=_target_rows(
                    target_formset
                ),
                attachments=_attachment_rows(
                    attachment_formset
                ),
                quoted_post_ids=(
                    request.POST.getlist(
                        "quoted_post_id"
                    )
                ),
            )
        except ValidationError as error:
            form.add_error(
                None,
                _validation_message(error),
            )

        else:
            _audit(
                request,
                thread,
                action=AuditLog.Action.CREATE,
            )

            opening_post = (
                thread.posts
                .order_by(
                    "created_at",
                    "id",
                )
                .first()
            )

            if opening_post is not None:
                _audit(
                    request,
                    opening_post,
                    action=(
                        AuditLog.Action.CREATE
                    ),
                )

            return redirect(
                "community:thread_detail",
                thread_id=thread.pk,
            )

    return render(
        request,
        "community/forum/thread_form.html",
        {
            "form": form,
            "target_formset":
                target_formset,
            "attachment_formset":
                attachment_formset,
            "board": board,
            "page_title":
                "Create Thread",
        },
    )


@login_required
@require_POST
def thread_draft_save(
    request,
    board_id,
):
    board = get_object_or_404(
        ForumBoard.objects
        .select_related("category")
        .prefetch_related("targets"),
        pk=board_id,
    )

    draft_form = ForumDraftContentForm(
        request.POST
    )

    target_formset = (
        ForumThreadTargetFormSet(
            request.POST,
            instance=ForumThread(
                board=board,
                created_by=request.user,
            ),
            prefix="targets",
        )
    )

    attachment_formset = (
        ForumPostAttachmentFormSet(
            request.POST,
            instance=ForumPost(),
            prefix="attachments",
        )
    )

    if (
        draft_form.is_valid()
        and target_formset.is_valid()
        and attachment_formset.is_valid()
    ):
        draft = None

        if request.POST.get("draft_id"):
            draft = get_object_or_404(
                ForumDraft,
                pk=request.POST["draft_id"],
                user=request.user,
            )

        save_thread_draft(
            user=request.user,
            board=board,
            title=(
                draft_form.cleaned_data[
                    "title"
                ]
            ),
            body=(
                draft_form.cleaned_data[
                    "body"
                ]
            ),
            target_data=_target_rows(
                target_formset,
                json_safe=True,
            ),
            attachment_links=(
                _attachment_rows(
                    attachment_formset
                )
            ),
            quoted_post_ids=(
                request.POST.getlist(
                    "quoted_post_id"
                )
            ),
            draft=draft,
        )

        messages.success(
            request,
            "Draft saved.",
        )

        return redirect(
            "community:draft_list"
        )

    messages.error(
        request,
        "The draft could not be saved.",
    )

    return redirect(
        "community:thread_create",
        board_id=board.pk,
    )


@login_required
def thread_detail(
    request,
    thread_id,
):
    thread = get_object_or_404(
        ForumThread.objects
        .select_related(
            "board",
            "board__category",
            "created_by",
            "merged_into",
        )
        .prefetch_related(
            "targets",
            "board__targets",
        ),
        pk=thread_id,
    )

    if thread.merged_into_id is not None:
        return redirect(
            "community:thread_detail",
            thread_id=thread.merged_into_id,
        )

    can_view_archived = (
        user_can_view_archived_forum(
            request.user
        )
    )

    if not user_can_access_thread(
        request.user,
        thread,
        include_archived=can_view_archived,
    ):
        raise PermissionDenied

    first_unread_post = (
        get_first_unread_post(
            request.user,
            thread,
        )
        if thread.archived_at is None
        else None
    )

    posts = list(
        thread.posts
        .select_related(
            "author",
            "edited_by",
            "archived_by",
        )
        .prefetch_related(
            "attachments",
            "quotes__quoted_post",
        )
        .order_by(
            "created_at",
            "id",
        )
    )

    for post in posts:
        post.show_content = (
            post.archived_at is None
            or can_view_archived
        )
        post.can_edit_for_user = (
            user_can_edit_post(
                request.user,
                post,
            )
        )
        post.can_archive_for_user = (
            user_can_archive_post(
                request.user,
                post,
            )
        )
        post.can_restore_for_user = (
            user_can_restore_post(
                request.user,
                post,
            )
        )
        post.can_report_for_user = (
            user_can_report_post(
                request.user,
                post,
            )
        )

    can_add_post = user_can_add_post(
        request.user,
        thread,
    )

    quoted_post = None
    post_form = None
    attachment_formset = None

    if can_add_post:
        quote_id = request.GET.get(
            "quote_post"
        )

        initial_body = ""

        if quote_id:
            try:
                quoted_post = (
                    ForumPost.objects
                    .select_related(
                        "thread",
                        "thread__board",
                        "thread__board__category",
                        "author",
                    )
                    .get(
                        pk=int(quote_id)
                    )
                )
            except (
                ForumPost.DoesNotExist,
                TypeError,
                ValueError,
            ):
                quoted_post = None

            if (
                quoted_post is not None
                and (
                    quoted_post.archived_at
                    is not None
                    or not user_can_access_thread(
                        request.user,
                        quoted_post.thread,
                    )
                )
            ):
                quoted_post = None

        if quoted_post is not None:
            author_name = (
                str(quoted_post.author)
                if quoted_post.author
                is not None
                else "Former member"
            )

            initial_body = (
                f"Quoted from {author_name}:\n"
                + "\n".join(
                    f"> {line}"
                    for line
                    in quoted_post.body
                    .splitlines()
                )
                + "\n\n"
            )

        post_form = ForumPostForm(
            initial={
                "body": initial_body,
            }
        )

        attachment_formset = (
            ForumPostAttachmentFormSet(
                instance=ForumPost(),
                prefix="attachments",
            )
        )

    if (
        thread.archived_at is None
        and thread.board.archived_at
        is None
        and thread.board.category
        .archived_at
        is None
    ):
        newest_active_post = next(
            (
                post
                for post in reversed(posts)
                if post.archived_at is None
            ),
            None,
        )

        if newest_active_post is not None:
            mark_thread_read(
                request.user,
                thread,
                newest_post=newest_active_post,
            )

    return render(
        request,
        "community/forum/thread_detail.html",
        {
            "thread": thread,
            "posts": posts,
            "post_form": post_form,
            "attachment_formset":
                attachment_formset,
            "quoted_post": quoted_post,
            "first_unread_post":
                first_unread_post,
            "is_following":
                ForumThreadSubscription
                .objects
                .filter(
                    user=request.user,
                    thread=thread,
                )
                .exists(),
            "can_add_post": can_add_post,
            "can_change_thread":
                user_can_change_thread(
                    request.user,
                    thread,
                ),
            "can_archive_thread":
                user_can_archive_thread(
                    request.user,
                    thread,
                ),
            "can_restore_thread":
                user_can_restore_thread(
                    request.user,
                    thread,
                ),
            "can_moderate":
                user_is_forum_moderator(
                    request.user
                ),
            "needs_attention_items":
                get_needs_attention_items(
                    request.user
                ),
        },
    )


@login_required
def thread_edit(
    request,
    thread_id,
):
    thread = get_object_or_404(
        ForumThread.objects
        .select_related(
            "board",
            "board__category",
        )
        .prefetch_related(
            "targets",
            "board__targets",
        ),
        pk=thread_id,
    )

    if not user_can_change_thread(
        request.user,
        thread,
    ):
        raise PermissionDenied

    old_value = _audit_values(
        thread
    )

    form = ForumThreadEditForm(
        request.POST or None,
        instance=thread,
    )

    target_formset = (
        ForumThreadTargetFormSet(
            request.POST or None,
            instance=thread,
            prefix="targets",
        )
    )

    if (
        request.method == "POST"
        and form.is_valid()
        and target_formset.is_valid()
    ):
        try:
            thread = edit_forum_thread(
                user=request.user,
                thread=thread,
                title=(
                    form.cleaned_data[
                        "title"
                    ]
                ),
                target_rows=_target_rows(
                    target_formset
                ),
            )
        except ValidationError as error:
            form.add_error(
                None,
                _validation_message(error),
            )

        else:
            _audit(
                request,
                thread,
                action=AuditLog.Action.UPDATE,
                old_value=old_value,
            )

            return redirect(
                "community:thread_detail",
                thread_id=thread.pk,
            )

    return render(
        request,
        "community/forum/thread_edit.html",
        {
            "form": form,
            "target_formset":
                target_formset,
            "thread": thread,
            "page_title":
                "Edit Thread",
        },
    )


@login_required
@require_POST
def thread_archive(
    request,
    thread_id,
):
    thread = get_object_or_404(
        ForumThread.objects
        .select_related(
            "board",
            "board__category",
        )
        .prefetch_related(
            "targets",
            "board__targets",
        ),
        pk=thread_id,
    )

    old_value = _audit_values(
        thread
    )

    thread = archive_forum_thread(
        user=request.user,
        thread=thread,
    )

    _audit(
        request,
        thread,
        action=AuditLog.Action.UPDATE,
        old_value=old_value,
        notes="Forum thread archived.",
    )

    return redirect(
        "community:board_detail",
        board_id=thread.board_id,
    )


@login_required
@require_POST
def thread_restore(
    request,
    thread_id,
):
    thread = get_object_or_404(
        ForumThread.objects
        .select_related(
            "board",
            "board__category",
        )
        .prefetch_related(
            "targets",
            "board__targets",
        ),
        pk=thread_id,
    )

    old_value = _audit_values(
        thread
    )

    thread = restore_forum_thread(
        user=request.user,
        thread=thread,
    )

    _audit(
        request,
        thread,
        action=AuditLog.Action.UPDATE,
        old_value=old_value,
        notes="Forum thread restored.",
    )

    return redirect(
        "community:thread_detail",
        thread_id=thread.pk,
    )


@login_required
@require_POST
def thread_pin(
    request,
    thread_id,
):
    thread = get_object_or_404(
        ForumThread,
        pk=thread_id,
    )

    old_value = _audit_values(
        thread
    )

    thread = set_thread_pinned(
        user=request.user,
        thread=thread,
        pinned=True,
    )

    _audit(
        request,
        thread,
        action=AuditLog.Action.UPDATE,
        old_value=old_value,
        notes="Forum thread pinned.",
    )

    return redirect(
        "community:thread_detail",
        thread_id=thread.pk,
    )


@login_required
@require_POST
def thread_unpin(
    request,
    thread_id,
):
    thread = get_object_or_404(
        ForumThread,
        pk=thread_id,
    )

    old_value = _audit_values(
        thread
    )

    thread = set_thread_pinned(
        user=request.user,
        thread=thread,
        pinned=False,
    )

    _audit(
        request,
        thread,
        action=AuditLog.Action.UPDATE,
        old_value=old_value,
        notes="Forum thread unpinned.",
    )

    return redirect(
        "community:thread_detail",
        thread_id=thread.pk,
    )


@login_required
@require_POST
def thread_lock(
    request,
    thread_id,
):
    thread = get_object_or_404(
        ForumThread,
        pk=thread_id,
    )

    old_value = _audit_values(
        thread
    )

    thread = set_thread_locked(
        user=request.user,
        thread=thread,
        locked=True,
    )

    _audit(
        request,
        thread,
        action=AuditLog.Action.UPDATE,
        old_value=old_value,
        notes="Forum thread locked.",
    )

    return redirect(
        "community:thread_detail",
        thread_id=thread.pk,
    )


@login_required
@require_POST
def thread_unlock(
    request,
    thread_id,
):
    thread = get_object_or_404(
        ForumThread,
        pk=thread_id,
    )

    old_value = _audit_values(
        thread
    )

    thread = set_thread_locked(
        user=request.user,
        thread=thread,
        locked=False,
    )

    _audit(
        request,
        thread,
        action=AuditLog.Action.UPDATE,
        old_value=old_value,
        notes="Forum thread unlocked.",
    )

    return redirect(
        "community:thread_detail",
        thread_id=thread.pk,
    )


@login_required
def thread_move(
    request,
    thread_id,
):
    if not user_is_forum_moderator(
        request.user
    ):
        raise PermissionDenied

    thread = get_object_or_404(
        ForumThread.objects
        .select_related(
            "board",
            "board__category",
        )
        .prefetch_related("targets"),
        pk=thread_id,
    )

    form = ForumThreadMoveForm(
        request.POST or None,
        board_queryset=(
            get_accessible_boards(
                request.user
            )
            .exclude(
                pk=thread.board_id
            )
        ),
    )

    if (
        request.method == "POST"
        and form.is_valid()
    ):
        old_value = _audit_values(
            thread
        )

        try:
            thread = move_forum_thread(
                user=request.user,
                thread=thread,
                destination_board=(
                    form.cleaned_data[
                        "destination_board"
                    ]
                ),
            )
        except ValidationError as error:
            form.add_error(
                None,
                _validation_message(error),
            )

        else:
            _audit(
                request,
                thread,
                action=AuditLog.Action.UPDATE,
                old_value=old_value,
                notes="Forum thread moved.",
            )

            return redirect(
                "community:thread_detail",
                thread_id=thread.pk,
            )

    return render(
        request,
        "community/forum/thread_move.html",
        {
            "thread": thread,
            "form": form,
        },
    )


@login_required
def thread_merge(
    request,
    thread_id,
):
    if not user_is_forum_moderator(
        request.user
    ):
        raise PermissionDenied

    source_thread = get_object_or_404(
        ForumThread.objects
        .select_related(
            "board",
            "board__category",
        )
        .prefetch_related("targets"),
        pk=thread_id,
    )

    form = ForumThreadMergeForm(
        request.POST or None,
        thread_queryset=(
            get_accessible_threads(
                request.user
            )
            .exclude(
                pk=source_thread.pk
            )
        ),
    )

    if (
        request.method == "POST"
        and form.is_valid()
    ):
        destination_thread = (
            form.cleaned_data[
                "destination_thread"
            ]
        )

        old_source = _audit_values(
            source_thread
        )
        old_destination = _audit_values(
            destination_thread
        )

        try:
            destination_thread = (
                merge_forum_threads(
                    user=request.user,
                    source_thread=source_thread,
                    destination_thread=(
                        destination_thread
                    ),
                )
            )
        except ValidationError as error:
            form.add_error(
                None,
                _validation_message(error),
            )

        else:
            source_thread.refresh_from_db()
            destination_thread.refresh_from_db()

            _audit(
                request,
                source_thread,
                action=AuditLog.Action.UPDATE,
                old_value=old_source,
                notes=(
                    "Forum thread merged into "
                    f"thread {destination_thread.pk}."
                ),
            )

            _audit(
                request,
                destination_thread,
                action=AuditLog.Action.UPDATE,
                old_value=old_destination,
                notes=(
                    "Forum thread received merged "
                    f"thread {source_thread.pk}."
                ),
            )

            return redirect(
                "community:thread_detail",
                thread_id=(
                    destination_thread.pk
                ),
            )

    return render(
        request,
        "community/forum/thread_merge.html",
        {
            "source_thread":
                source_thread,
            "form": form,
        },
    )


@login_required
def thread_split(
    request,
    thread_id,
):
    if not user_is_forum_moderator(
        request.user
    ):
        raise PermissionDenied

    source_thread = get_object_or_404(
        ForumThread.objects
        .select_related(
            "board",
            "board__category",
        )
        .prefetch_related("targets"),
        pk=thread_id,
    )

    post_queryset = (
        source_thread.posts
        .select_related("author")
        .order_by(
            "created_at",
            "id",
        )
    )

    form = ForumThreadSplitForm(
        request.POST or None,
        board_queryset=(
            get_accessible_boards(
                request.user
            )
        ),
        post_queryset=post_queryset,
    )

    if (
        request.method == "POST"
        and form.is_valid()
    ):
        selected_posts = list(
            form.cleaned_data["posts"]
        )

        source_old_value = (
            _audit_values(
                source_thread
            )
        )

        post_old_values = {
            post.pk: _audit_values(post)
            for post in selected_posts
        }

        try:
            new_thread = (
                split_forum_thread(
                    user=request.user,
                    source_thread=(
                        source_thread
                    ),
                    posts=selected_posts,
                    destination_board=(
                        form.cleaned_data[
                            "destination_board"
                        ]
                    ),
                    title=(
                        form.cleaned_data[
                            "title"
                        ]
                    ),
                )
            )
        except ValidationError as error:
            form.add_error(
                None,
                _validation_message(error),
            )

        else:
            source_thread.refresh_from_db()

            _audit(
                request,
                source_thread,
                action=AuditLog.Action.UPDATE,
                old_value=source_old_value,
                notes="Forum thread split.",
            )

            _audit(
                request,
                new_thread,
                action=AuditLog.Action.CREATE,
                notes=(
                    "Forum thread created "
                    "from a split."
                ),
            )

            for post in selected_posts:
                post.refresh_from_db()

                _audit(
                    request,
                    post,
                    action=AuditLog.Action.UPDATE,
                    old_value=(
                        post_old_values[
                            post.pk
                        ]
                    ),
                    notes=(
                        "Forum post moved "
                        "during thread split."
                    ),
                )

            return redirect(
                "community:thread_detail",
                thread_id=new_thread.pk,
            )

    return render(
        request,
        "community/forum/thread_split.html",
        {
            "source_thread":
                source_thread,
            "form": form,
        },
    )


@login_required
def thread_move_posts(
    request,
    thread_id,
):
    if not user_is_forum_moderator(
        request.user
    ):
        raise PermissionDenied

    source_thread = get_object_or_404(
        ForumThread,
        pk=thread_id,
    )

    post_queryset = (
        source_thread.posts
        .select_related("author")
        .order_by(
            "created_at",
            "id",
        )
    )

    form = ForumPostMoveForm(
        request.POST or None,
        thread_queryset=(
            get_accessible_threads(
                request.user
            )
            .exclude(
                pk=source_thread.pk
            )
        ),
        post_queryset=post_queryset,
    )

    if (
        request.method == "POST"
        and form.is_valid()
    ):
        selected_posts = list(
            form.cleaned_data["posts"]
        )

        post_old_values = {
            post.pk: _audit_values(post)
            for post in selected_posts
        }

        destination_thread = (
            form.cleaned_data[
                "destination_thread"
            ]
        )

        try:
            move_forum_posts(
                user=request.user,
                posts=selected_posts,
                destination_thread=(
                    destination_thread
                ),
            )
        except ValidationError as error:
            form.add_error(
                None,
                _validation_message(error),
            )

        else:
            for post in selected_posts:
                post.refresh_from_db()

                _audit(
                    request,
                    post,
                    action=AuditLog.Action.UPDATE,
                    old_value=(
                        post_old_values[
                            post.pk
                        ]
                    ),
                    notes=(
                        "Forum post moved "
                        "between threads."
                    ),
                )

            return redirect(
                "community:thread_detail",
                thread_id=(
                    destination_thread.pk
                ),
            )

    return render(
        request,
        "community/forum/thread_move_posts.html",
        {
            "source_thread":
                source_thread,
            "form": form,
        },
    )


@login_required
@require_POST
def thread_follow(
    request,
    thread_id,
):
    thread = get_object_or_404(
        ForumThread.objects
        .select_related(
            "board",
            "board__category",
        )
        .prefetch_related(
            "targets",
            "board__targets",
        ),
        pk=thread_id,
    )

    subscribe_to_thread(
        request.user,
        thread,
    )

    return redirect(
        "community:thread_detail",
        thread_id=thread.pk,
    )


@login_required
@require_POST
def thread_unfollow(
    request,
    thread_id,
):
    thread = get_object_or_404(
        ForumThread,
        pk=thread_id,
    )

    unsubscribe_from_thread(
        request.user,
        thread,
    )

    return redirect(
        "community:thread_detail",
        thread_id=thread.pk,
    )


@login_required
@require_POST
def post_create(
    request,
    thread_id,
):
    thread = get_object_or_404(
        ForumThread.objects
        .select_related(
            "board",
            "board__category",
        )
        .prefetch_related(
            "targets",
            "board__targets",
        ),
        pk=thread_id,
    )

    if not user_can_add_post(
        request.user,
        thread,
    ):
        raise PermissionDenied

    post_shell = ForumPost(
        thread=thread,
        author=request.user,
    )

    form = ForumPostForm(
        request.POST,
        instance=post_shell,
    )

    attachment_formset = (
        ForumPostAttachmentFormSet(
            request.POST,
            instance=post_shell,
            prefix="attachments",
        )
    )

    if (
        form.is_valid()
        and attachment_formset.is_valid()
    ):
        try:
            post = create_forum_post(
                user=request.user,
                thread=thread,
                body=(
                    form.cleaned_data[
                        "body"
                    ]
                ),
                attachments=(
                    _attachment_rows(
                        attachment_formset
                    )
                ),
                quoted_post_ids=(
                    request.POST.getlist(
                        "quoted_post_id"
                    )
                ),
            )
        except ValidationError as error:
            messages.error(
                request,
                _validation_message(error),
            )

        else:
            _audit(
                request,
                post,
                action=AuditLog.Action.CREATE,
            )

            return redirect(
                reverse(
                    "community:thread_detail",
                    args=[thread.pk],
                )
                + f"#post-{post.pk}"
            )

    else:
        messages.error(
            request,
            "The post could not be created.",
        )

    return redirect(
        "community:thread_detail",
        thread_id=thread.pk,
    )


@login_required
@require_POST
def post_draft_save(
    request,
    thread_id,
):
    thread = get_object_or_404(
        ForumThread.objects
        .select_related(
            "board",
            "board__category",
        )
        .prefetch_related(
            "targets",
            "board__targets",
        ),
        pk=thread_id,
    )

    form = ForumDraftContentForm(
        request.POST
    )

    attachment_formset = (
        ForumPostAttachmentFormSet(
            request.POST,
            instance=ForumPost(),
            prefix="attachments",
        )
    )

    if (
        form.is_valid()
        and attachment_formset.is_valid()
    ):
        draft = None

        if request.POST.get("draft_id"):
            draft = get_object_or_404(
                ForumDraft,
                pk=request.POST["draft_id"],
                user=request.user,
            )

        save_post_draft(
            user=request.user,
            thread=thread,
            body=(
                form.cleaned_data[
                    "body"
                ]
            ),
            attachment_links=(
                _attachment_rows(
                    attachment_formset
                )
            ),
            quoted_post_ids=(
                request.POST.getlist(
                    "quoted_post_id"
                )
            ),
            draft=draft,
        )

        messages.success(
            request,
            "Draft saved.",
        )

        return redirect(
            "community:draft_list"
        )

    messages.error(
        request,
        "The draft could not be saved.",
    )

    return redirect(
        "community:thread_detail",
        thread_id=thread.pk,
    )


@login_required
def post_edit(
    request,
    post_id,
):
    post = get_object_or_404(
        ForumPost.objects
        .select_related(
            "thread",
            "thread__board",
            "thread__board__category",
            "author",
        )
        .prefetch_related(
            "attachments",
            "thread__targets",
            "thread__board__targets",
        ),
        pk=post_id,
    )

    if not user_can_edit_post(
        request.user,
        post,
    ):
        raise PermissionDenied

    old_value = _audit_values(
        post
    )

    form = ForumPostForm(
        request.POST or None,
        instance=post,
    )

    attachment_formset = (
        ForumPostAttachmentFormSet(
            request.POST or None,
            instance=post,
            prefix="attachments",
        )
    )

    if (
        request.method == "POST"
        and form.is_valid()
        and attachment_formset.is_valid()
    ):
        try:
            with transaction.atomic():
                post = edit_forum_post(
                    user=request.user,
                    post=post,
                    body=(
                        form.cleaned_data[
                            "body"
                        ]
                    ),
                )

                attachment_formset.instance = (
                    post
                )
                attachment_formset.save()

        except ValidationError as error:
            form.add_error(
                None,
                _validation_message(error),
            )

        else:
            _audit(
                request,
                post,
                action=AuditLog.Action.UPDATE,
                old_value=old_value,
            )

            return redirect(
                reverse(
                    "community:thread_detail",
                    args=[post.thread_id],
                )
                + f"#post-{post.pk}"
            )

    return render(
        request,
        "community/forum/post_edit.html",
        {
            "post": post,
            "form": form,
            "attachment_formset":
                attachment_formset,
        },
    )


@login_required
@require_POST
def post_archive(
    request,
    post_id,
):
    post = get_object_or_404(
        ForumPost.objects
        .select_related(
            "thread",
            "thread__board",
            "thread__board__category",
        )
        .prefetch_related(
            "thread__targets",
            "thread__board__targets",
            "attachments",
            "quotes",
        ),
        pk=post_id,
    )

    old_value = _audit_values(
        post
    )

    post = archive_forum_post(
        user=request.user,
        post=post,
    )

    _audit(
        request,
        post,
        action=AuditLog.Action.UPDATE,
        old_value=old_value,
        notes="Forum post archived.",
    )

    return redirect(
        "community:thread_detail",
        thread_id=post.thread_id,
    )


@login_required
@require_POST
def post_restore(
    request,
    post_id,
):
    post = get_object_or_404(
        ForumPost.objects
        .select_related(
            "thread",
            "thread__board",
            "thread__board__category",
        )
        .prefetch_related(
            "thread__targets",
            "thread__board__targets",
            "attachments",
            "quotes",
        ),
        pk=post_id,
    )

    old_value = _audit_values(
        post
    )

    post = restore_forum_post(
        user=request.user,
        post=post,
    )

    _audit(
        request,
        post,
        action=AuditLog.Action.UPDATE,
        old_value=old_value,
        notes="Forum post restored.",
    )

    return redirect(
        reverse(
            "community:thread_detail",
            args=[post.thread_id],
        )
        + f"#post-{post.pk}"
    )


@login_required
def post_quote(
    request,
    post_id,
):
    post = get_object_or_404(
        ForumPost.objects
        .select_related(
            "thread",
            "thread__board",
            "thread__board__category",
        )
        .prefetch_related(
            "thread__targets",
            "thread__board__targets",
        ),
        pk=post_id,
    )

    if (
        post.archived_at is not None
        or not user_can_add_post(
            request.user,
            post.thread,
        )
    ):
        raise PermissionDenied

    return redirect(
        reverse(
            "community:thread_detail",
            args=[post.thread_id],
        )
        + f"?quote_post={post.pk}"
        + "#reply"
    )


@login_required
def post_report(
    request,
    post_id,
):
    post = get_object_or_404(
        ForumPost.objects
        .select_related(
            "thread",
            "thread__board",
            "thread__board__category",
            "author",
        )
        .prefetch_related(
            "thread__targets",
            "thread__board__targets",
        ),
        pk=post_id,
    )

    if not user_can_report_post(
        request.user,
        post,
    ):
        raise PermissionDenied

    form = ForumPostReportForm(
        request.POST or None
    )

    if (
        request.method == "POST"
        and form.is_valid()
    ):
        try:
            report = create_post_report(
                user=request.user,
                post=post,
                reason=(
                    form.cleaned_data[
                        "reason"
                    ]
                ),
            )
        except ValidationError as error:
            form.add_error(
                None,
                _validation_message(error),
            )

        else:
            _audit(
                request,
                report,
                action=AuditLog.Action.CREATE,
                notes="Forum post reported.",
            )

            return redirect(
                reverse(
                    "community:thread_detail",
                    args=[post.thread_id],
                )
                + f"#post-{post.pk}"
            )

    return render(
        request,
        "community/forum/post_report.html",
        {
            "post": post,
            "form": form,
        },
    )


@login_required
def draft_list(request):
    if not user_is_forum_member(
        request.user
    ):
        raise PermissionDenied

    drafts = (
        ForumDraft.objects
        .filter(
            user=request.user,
        )
        .select_related(
            "board",
            "thread",
            "thread__board",
        )
        .order_by(
            "-updated_at",
        )
    )

    return render(
        request,
        "community/forum/draft_list.html",
        {
            "drafts": drafts,
        },
    )


@login_required
@require_POST
def draft_delete(
    request,
    draft_id,
):
    draft = get_object_or_404(
        ForumDraft,
        pk=draft_id,
        user=request.user,
    )

    draft.delete()

    return redirect(
        "community:draft_list"
    )


@login_required
@require_POST
def draft_publish(
    request,
    draft_id,
):
    draft = get_object_or_404(
        ForumDraft.objects
        .select_related(
            "board",
            "thread",
            "thread__board",
            "thread__board__category",
        ),
        pk=draft_id,
        user=request.user,
    )

    try:
        result = publish_forum_draft(
            user=request.user,
            draft=draft,
        )
    except ValidationError as error:
        messages.error(
            request,
            _validation_message(error),
        )

        return redirect(
            "community:draft_list"
        )

    if isinstance(
        result,
        ForumThread,
    ):
        _audit(
            request,
            result,
            action=AuditLog.Action.CREATE,
            notes=(
                "Forum thread published "
                "from draft."
            ),
        )

        opening_post = (
            result.posts
            .order_by(
                "created_at",
                "id",
            )
            .first()
        )

        if opening_post is not None:
            _audit(
                request,
                opening_post,
                action=AuditLog.Action.CREATE,
                notes=(
                    "Opening post published "
                    "from draft."
                ),
            )

        return redirect(
            "community:thread_detail",
            thread_id=result.pk,
        )

    _audit(
        request,
        result,
        action=AuditLog.Action.CREATE,
        notes=(
            "Forum post published "
            "from draft."
        ),
    )

    return redirect(
        reverse(
            "community:thread_detail",
            args=[result.thread_id],
        )
        + f"#post-{result.pk}"
    )