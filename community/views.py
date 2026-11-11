from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import (
    PermissionDenied,
    ValidationError,
)
from django.db import transaction
from django.http import Http404
from django.db.models import Count, Q
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
    resolve_post_report,
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

    boards_queryset = get_accessible_boards(
        request.user,
        include_archived=show_archived,
    )

    if show_archived:
        boards_queryset = (
            boards_queryset.annotate(
                thread_count=Count(
                    "threads",
                    distinct=True,
                ),
                post_count=Count(
                    "threads__posts",
                    distinct=True,
                ),
            )
        )
    else:
        boards_queryset = (
            boards_queryset.annotate(
                thread_count=Count(
                    "threads",
                    filter=Q(
                        threads__archived_at__isnull=True,
                    ),
                    distinct=True,
                ),
                post_count=Count(
                    "threads__posts",
                    filter=Q(
                        threads__archived_at__isnull=True,
                        threads__posts__archived_at__isnull=True,
                    ),
                    distinct=True,
                ),
            )
        )

    boards = list(
        boards_queryset
    )

    boards_by_category = {}

    for board in boards:
        board.has_unread = (
            board_has_unread_threads(
                request.user,
                board,
            )
            if board.archived_at is None
            and board.category.archived_at is None
            else False
        )

        accessible_thread_ids = list(
            get_accessible_threads(
                request.user,
                board=board,
                include_archived=show_archived,
            ).values_list(
                "id",
                flat=True,
            )
        )

        board.latest_visible_post = (
            ForumPost.objects
            .filter(
                thread_id__in=accessible_thread_ids,
                archived_at__isnull=True,
            )
            .select_related(
                "author",
                "thread",
            )
            .order_by(
                "-created_at",
                "-id",
            )
            .first()
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
                "boards": boards_by_category.get(
                    category.pk,
                    [],
                ),
            }
        )

    return render(
        request,
        "community/tavern/tavern_main_desktop.html",
        {
            "category_sections": category_sections,
            "show_archived": show_archived,
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
    ).strip()[:150]

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
        action=AuditLog.Action.ARCHIVE,
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
        action=AuditLog.Action.RESTORE,
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

    can_view_archived = (
        user_can_view_archived_forum(
            request.user
        )
    )

    show_archived = (
        request.GET.get("archived") == "1"
        and can_view_archived
    )

    if not user_can_access_board(
        request.user,
        board,
        include_archived=can_view_archived,
    ):
        raise PermissionDenied

    threads_queryset = (
        get_accessible_threads(
            request.user,
            board=board,
            include_archived=show_archived,
        )
    )

    if show_archived:
        threads_queryset = (
            threads_queryset.annotate(
                post_count=Count(
                    "posts",
                    distinct=True,
                )
            )
        )
    else:
        threads_queryset = (
            threads_queryset.annotate(
                post_count=Count(
                    "posts",
                    filter=Q(
                        posts__archived_at__isnull=True,
                    ),
                    distinct=True,
                )
            )
        )

    threads = list(
        threads_queryset
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

        thread.latest_visible_post = (
            thread.posts
            .filter(
                archived_at__isnull=True,
            )
            .select_related("author")
            .order_by(
                "-created_at",
                "-id",
            )
            .first()
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
                can_view_archived,
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
        action=AuditLog.Action.ARCHIVE,
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
        action=AuditLog.Action.RESTORE,
        old_value=old_value,
        notes="Forum board restored.",
    )

    if user_can_access_board(
        request.user,
        board,
        include_archived=(
            user_can_view_archived_forum(
                request.user
            )
        ),
    ):
        return redirect(
            "community:board_detail",
            board_id=board.pk,
        )

    return redirect(
        "community:forum_index"
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
        action=AuditLog.Action.LOCK,
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
        action=AuditLog.Action.UNLOCK,
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


def _get_owned_draft(request, draft_id, *, draft_type, board=None, thread=None):
    if not draft_id:
        return None

    if not str(draft_id).isdecimal() or len(str(draft_id)) > 20:
        raise Http404

    draft = get_object_or_404(
        ForumDraft,
        pk=draft_id,
        user=request.user,
    )

    if draft.draft_type != draft_type:
        raise PermissionDenied

    if board is not None and draft.board_id != board.pk:
        raise PermissionDenied

    if thread is not None and draft.thread_id != thread.pk:
        raise PermissionDenied

    return draft


def _draft_formset(formset_class, *, instance, prefix, data=None, initial=None):
    # Draft rows are not persisted as related model instances.
    # Add enough blank inline forms to render all saved rows.
    rows = initial or []
    if data is None and rows:
        formset_class = type(
            "RestoredDraftFormSet",
            (formset_class,),
            {"extra": max(1, len(rows))},
        )

    return formset_class(
        data,
        instance=instance,
        prefix=prefix,
        initial=rows if data is None else None,
    )


def _draft_target_initial(draft):
    return [
        {
            field_name: row.get(f"{field_name}_id")
            for field_name in FORUM_TARGET_FIELDS
        }
        for row in draft.target_data
    ]


def _render_thread_draft_form(
    request,
    board,
    *,
    draft,
    form,
    target_formset,
    attachment_formset,
):
    return render(
        request,
        "community/forum/thread_form.html",
        {
            "form": form,
            "target_formset": target_formset,
            "attachment_formset": attachment_formset,
            "board": board,
            "draft": draft,
            "draft_quote_ids": draft.quoted_post_ids if draft else [],
            "page_title": "Create Thread",
        },
    )


@login_required
def thread_create(request, board_id):
    board = get_object_or_404(
        ForumBoard.objects
        .select_related("category")
        .prefetch_related("targets", "thread_creation_targets"),
        pk=board_id,
    )

    if not user_can_create_thread(request.user, board):
        raise PermissionDenied

    draft_id = (
        request.POST.get("draft_id")
        if request.method == "POST"
        else request.GET.get("draft")
    )
    draft = _get_owned_draft(
        request,
        draft_id,
        draft_type=ForumDraft.DraftType.THREAD,
        board=board,
    )

    thread_shell = ForumThread(board=board, created_by=request.user)
    post_shell = ForumPost(author=request.user)
    data = request.POST if request.method == "POST" else None

    form = ForumThreadCreateForm(
        data,
        initial={"title": draft.title, "body": draft.body} if draft else None,
    )
    target_formset = _draft_formset(
        ForumThreadTargetFormSet,
        instance=thread_shell,
        prefix="targets",
        data=data,
        initial=_draft_target_initial(draft) if draft else None,
    )
    attachment_formset = _draft_formset(
        ForumPostAttachmentFormSet,
        instance=post_shell,
        prefix="attachments",
        data=data,
        initial=draft.attachment_links if draft else None,
    )

    if request.method == "POST":
        valid_form = form.is_valid()
        valid_targets = target_formset.is_valid()
        valid_attachments = attachment_formset.is_valid()

        if valid_form and valid_targets and valid_attachments:
            try:
                with transaction.atomic():
                    thread = create_forum_thread(
                        user=request.user,
                        board=board,
                        title=form.cleaned_data["title"],
                        body=form.cleaned_data["body"],
                        target_rows=_target_rows(target_formset),
                        attachments=_attachment_rows(attachment_formset),
                        quoted_post_ids=request.POST.getlist("quoted_post_id"),
                    )
                    _audit(
                        request,
                        thread,
                        action=AuditLog.Action.CREATE,
                    )
                    opening_post = (
                        thread.posts.order_by("created_at", "id").first()
                    )
                    if opening_post is not None:
                        _audit(
                            request,
                            opening_post,
                            action=AuditLog.Action.CREATE,
                        )
                    if draft is not None:
                        draft.delete()
            except ValidationError as error:
                form.add_error(None, _validation_message(error))
            else:
                return redirect(
                    "community:thread_detail",
                    thread_id=thread.pk,
                )

    return _render_thread_draft_form(
        request,
        board,
        draft=draft,
        form=form,
        target_formset=target_formset,
        attachment_formset=attachment_formset,
    )


@login_required
@require_POST
def thread_draft_save(request, board_id):
    board = get_object_or_404(
        ForumBoard.objects.select_related("category").prefetch_related("targets"),
        pk=board_id,
    )

    if not user_can_create_thread(request.user, board):
        raise PermissionDenied

    draft = _get_owned_draft(
        request,
        request.POST.get("draft_id"),
        draft_type=ForumDraft.DraftType.THREAD,
        board=board,
    )
    form = ForumDraftContentForm(request.POST)
    target_formset = _draft_formset(
        ForumThreadTargetFormSet,
        instance=ForumThread(board=board, created_by=request.user),
        prefix="targets",
        data=request.POST,
    )
    attachment_formset = _draft_formset(
        ForumPostAttachmentFormSet,
        instance=ForumPost(author=request.user),
        prefix="attachments",
        data=request.POST,
    )

    valid_form = form.is_valid()
    valid_targets = target_formset.is_valid()
    valid_attachments = attachment_formset.is_valid()
    if valid_form and valid_targets and valid_attachments:
        try:
            save_thread_draft(
                user=request.user,
                board=board,
                title=form.cleaned_data["title"],
                body=form.cleaned_data["body"],
                target_data=_target_rows(target_formset, json_safe=True),
                attachment_links=_attachment_rows(attachment_formset),
                quoted_post_ids=request.POST.getlist("quoted_post_id"),
                draft=draft,
            )
        except ValidationError as error:
            form.add_error(None, _validation_message(error))
        else:
            messages.success(request, "Draft saved.")
            return redirect("community:draft_list")

    return _render_thread_draft_form(
        request,
        board,
        draft=draft,
        form=form,
        target_formset=target_formset,
        attachment_formset=attachment_formset,
    )


def _render_thread_detail_page(
    request,
    thread,
    *,
    post_form=None,
    attachment_formset=None,
    quote_id=None,
    draft=None,
    draft_quote_ids=None,
):
    can_view_archived = (
        user_can_view_archived_forum(
            request.user
        )
    )

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

    latest_active_post = next(
        (
            post
            for post in reversed(posts)
            if post.archived_at is None
        ),
        None,
    )

    can_add_post = user_can_add_post(
        request.user,
        thread,
    )

    quoted_post = None

    if (
        can_add_post
        and quote_id
    ):
        try:
            quoted_post = (
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

    if (
        can_add_post
        and post_form is None
    ):
        initial_body = ""

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

    if (
        can_add_post
        and attachment_formset is None
    ):
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
        .archived_at is None
        and latest_active_post is not None
    ):
        mark_thread_read(
            request.user,
            thread,
            newest_post=latest_active_post,
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
            "draft": draft,
            "draft_quote_ids": draft_quote_ids or [],
            "latest_active_post":
                latest_active_post,
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
def thread_detail(request, thread_id):
    thread = get_object_or_404(
        ForumThread.objects
        .select_related("board", "board__category", "created_by", "merged_into")
        .prefetch_related("targets", "board__targets"),
        pk=thread_id,
    )
    can_view_archived = user_can_view_archived_forum(request.user)

    if thread.merged_into_id is not None:
        # A draft tied to a merged source thread cannot be resumed at a
        # different thread without explicit author action.
        if request.GET.get("draft"):
            raise PermissionDenied
        destination_thread = get_object_or_404(
            ForumThread.objects
            .select_related("board", "board__category")
            .prefetch_related("targets", "board__targets"),
            pk=thread.merged_into_id,
        )
        if not user_can_access_thread(
            request.user,
            destination_thread,
            include_archived=can_view_archived,
        ):
            raise PermissionDenied
        return redirect(
            "community:thread_detail",
            thread_id=destination_thread.pk,
        )

    if not user_can_access_thread(
        request.user,
        thread,
        include_archived=can_view_archived,
    ):
        raise PermissionDenied

    draft = _get_owned_draft(
        request,
        request.GET.get("draft"),
        draft_type=ForumDraft.DraftType.POST,
        thread=thread,
    )
    if draft is not None and not user_can_add_post(request.user, thread):
        raise PermissionDenied

    post_form = None
    attachment_formset = None
    quote_ids = draft.quoted_post_ids if draft is not None else []
    if draft is not None:
        post_form = ForumPostForm(initial={"body": draft.body})
        attachment_formset = _draft_formset(
            ForumPostAttachmentFormSet,
            instance=ForumPost(thread=thread, author=request.user),
            prefix="attachments",
            initial=draft.attachment_links,
        )

    return _render_thread_detail_page(
        request,
        thread,
        post_form=post_form,
        attachment_formset=attachment_formset,
        quote_id=quote_ids[0] if quote_ids else request.GET.get("quote_post"),
        draft=draft,
        draft_quote_ids=quote_ids,
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
        "community/forum/thread_form.html",
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
        action=AuditLog.Action.ARCHIVE,
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
        action=AuditLog.Action.RESTORE,
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
        action=AuditLog.Action.PIN,
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
        action=AuditLog.Action.UNPIN,
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
        action=AuditLog.Action.LOCK,
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
        action=AuditLog.Action.UNLOCK,
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
                action=AuditLog.Action.MOVE,
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
                action=AuditLog.Action.MERGE,
                old_value=old_source,
                notes=(
                    "Forum thread merged into "
                    f"thread {destination_thread.pk}."
                ),
            )

            _audit(
                request,
                destination_thread,
                action=AuditLog.Action.MERGE,
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
                action=AuditLog.Action.SPLIT,
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
                    action=AuditLog.Action.MOVE,
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
                    action=AuditLog.Action.MOVE,
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
def post_create(request, thread_id):
    thread = get_object_or_404(
        ForumThread.objects
        .select_related("board", "board__category")
        .prefetch_related("targets", "board__targets"),
        pk=thread_id,
    )

    if not user_can_add_post(request.user, thread):
        raise PermissionDenied

    draft = _get_owned_draft(
        request,
        request.POST.get("draft_id"),
        draft_type=ForumDraft.DraftType.POST,
        thread=thread,
    )
    post_shell = ForumPost(thread=thread, author=request.user)
    form = ForumPostForm(request.POST, instance=post_shell)
    attachment_formset = _draft_formset(
        ForumPostAttachmentFormSet,
        instance=post_shell,
        prefix="attachments",
        data=request.POST,
    )

    valid_form = form.is_valid()
    valid_attachments = attachment_formset.is_valid()
    if valid_form and valid_attachments:
        try:
            with transaction.atomic():
                post = create_forum_post(
                    user=request.user,
                    thread=thread,
                    body=form.cleaned_data["body"],
                    attachments=_attachment_rows(attachment_formset),
                    quoted_post_ids=request.POST.getlist("quoted_post_id"),
                )
                _audit(
                    request,
                    post,
                    action=AuditLog.Action.CREATE,
                )
                if draft is not None:
                    draft.delete()
        except ValidationError as error:
            form.add_error(None, _validation_message(error))
        else:
            return redirect(
                reverse("community:thread_detail", args=[thread.pk])
                + f"#post-{post.pk}"
            )

    quote_ids = request.POST.getlist("quoted_post_id")
    return _render_thread_detail_page(
        request,
        thread,
        post_form=form,
        attachment_formset=attachment_formset,
        quote_id=quote_ids[0] if quote_ids else None,
        draft=draft,
        draft_quote_ids=quote_ids,
    )


@login_required
@require_POST
def post_draft_save(request, thread_id):
    thread = get_object_or_404(
        ForumThread.objects
        .select_related("board", "board__category")
        .prefetch_related("targets", "board__targets"),
        pk=thread_id,
    )

    if not user_can_add_post(request.user, thread):
        raise PermissionDenied

    draft = _get_owned_draft(
        request,
        request.POST.get("draft_id"),
        draft_type=ForumDraft.DraftType.POST,
        thread=thread,
    )
    form = ForumDraftContentForm(request.POST)
    attachment_formset = _draft_formset(
        ForumPostAttachmentFormSet,
        instance=ForumPost(thread=thread, author=request.user),
        prefix="attachments",
        data=request.POST,
    )

    valid_form = form.is_valid()
    valid_attachments = attachment_formset.is_valid()
    if valid_form and valid_attachments:
        try:
            save_post_draft(
                user=request.user,
                thread=thread,
                body=form.cleaned_data["body"],
                attachment_links=_attachment_rows(attachment_formset),
                quoted_post_ids=request.POST.getlist("quoted_post_id"),
                draft=draft,
            )
        except ValidationError as error:
            form.add_error(None, _validation_message(error))
        else:
            messages.success(request, "Draft saved.")
            return redirect("community:draft_list")

    quote_ids = request.POST.getlist("quoted_post_id")
    return _render_thread_detail_page(
        request,
        thread,
        post_form=ForumPostForm(request.POST),
        attachment_formset=attachment_formset,
        quote_id=quote_ids[0] if quote_ids else None,
        draft=draft,
        draft_quote_ids=quote_ids,
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
            "needs_attention_items":
                get_needs_attention_items(
                    request.user
                ),
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
        action=AuditLog.Action.ARCHIVE,
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
        action=AuditLog.Action.RESTORE,
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
@require_POST
def post_report_review(
    request,
    report_id,
):
    if not user_is_forum_moderator(
        request.user
    ):
        raise PermissionDenied

    report = get_object_or_404(
        ForumPostReport.objects
        .select_related(
            "post",
            "post__thread",
            "post__thread__board",
            "post__thread__board__category",
            "reporter",
            "reviewed_by",
        ),
        pk=report_id,
    )

    old_value = _audit_values(
        report
    )

    try:
        report = resolve_post_report(
            user=request.user,
            report=report,
            status=request.POST.get(
                "status",
                "",
            ),
            resolution_note=(
                request.POST.get(
                    "resolution_note",
                    "",
                )
            ),
        )
    except ValidationError as error:
        messages.error(
            request,
            _validation_message(error),
        )

        return redirect(
            reverse(
                "community:thread_detail",
                args=[report.post.thread_id],
            )
            + f"#post-{report.post_id}"
        )

    _audit(
        request,
        report,
        action=AuditLog.Action.UPDATE,
        old_value=old_value,
        notes="Forum post report reviewed.",
    )

    return redirect(
        reverse(
            "community:thread_detail",
            args=[report.post.thread_id],
        )
        + f"#post-{report.post_id}"
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
