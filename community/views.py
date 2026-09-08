from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import AccountStatus
from accounts.needs_attention import get_needs_attention_items
from audit.models import AuditLog
from audit.services import record_audit_event

from .forms import (
    CommentForm,
    POST_TARGET_FIELDS,
    PostForm,
    PostTargetFormSet,
    ReplyForm,
)
from .models import Comment, Post, PostTarget
from .services import (
    get_visible_posts,
    user_can_view_post,
)


def is_member(user):
    return (
        user.is_authenticated
        and user.is_active
        and user.account_status == AccountStatus.MEMBER
    )


def get_tavern_template(request):
    user_agent = request.META.get(
        "HTTP_USER_AGENT",
        "",
    ).lower()

    is_mobile = any(
        mobile_term in user_agent
        for mobile_term in (
            "android",
            "iphone",
            "ipod",
            "mobile",
        )
    )

    if is_mobile:
        return (
            "community/tavern/"
            "tavern_main_mobile.html"
        )

    return (
        "community/tavern/"
        "tavern_main_desktop.html"
    )


def can_view_post(user, post):
    if post.is_deleted:
        return False

    if (
        user.is_authenticated
        and user.has_perm("community.view_post")
    ):
        return True

    return user_can_view_post(
        user,
        post,
    )


def can_edit_post(user, post):
    if post.is_deleted:
        return False

    if not is_member(user):
        return False

    return (
        post.author_id == user.id
        or user.has_perm(
            "community.change_post"
        )
    )


def can_delete_post(user, post):
    if post.is_deleted:
        return False

    if not is_member(user):
        return False

    return (
        post.author_id == user.id
        or user.has_perm(
            "community.delete_post"
        )
    )


def can_edit_comment(user, comment):
    if comment.post.is_deleted:
        return False

    if not is_member(user):
        return False

    return (
        comment.author_id == user.id
        or user.has_perm(
            "community.change_comment"
        )
    )


def can_delete_comment(user, comment):
    if comment.post.is_deleted:
        return False

    if not is_member(user):
        return False

    return (
        comment.author_id == user.id
        or user.has_perm(
            "community.delete_comment"
        )
    )


def post_target_values(post):
    targets = []

    for target in post.targets.all().order_by("id"):
        targets.append(
            {
                "user": (
                    str(target.user)
                    if target.user
                    else None
                ),
                "citizenship_class": (
                    str(target.citizenship_class)
                    if target.citizenship_class
                    else None
                ),
                "social_rank": (
                    str(target.social_rank)
                    if target.social_rank
                    else None
                ),
                "office": (
                    str(target.office)
                    if target.office
                    else None
                ),
                "chapter": (
                    str(target.chapter)
                    if target.chapter
                    else None
                ),
                "household": (
                    str(target.household)
                    if target.household
                    else None
                ),
                "governance_body": (
                    str(target.governance_body)
                    if target.governance_body
                    else None
                ),
                "order": (
                    str(target.order)
                    if target.order
                    else None
                ),
                "order_rank": (
                    str(target.order_rank)
                    if target.order_rank
                    else None
                ),
                "community_group": (
                    str(target.community_group)
                    if target.community_group
                    else None
                ),
                "household_leadership_type": (
                    str(
                        target.household_leadership_type
                    )
                    if target.household_leadership_type
                    else None
                ),
            }
        )

    return targets


def post_values(post):
    return {
        "id": post.pk,
        "author": str(post.author),
        "previous_version_id":
            post.previous_version_id,
        "body": post.body,
        "visibility": post.visibility,
        "targets": post_target_values(post),
        "is_official": post.is_official,
        "is_pinned": post.is_pinned,
        "is_locked": post.is_locked,
        "is_deleted": post.is_deleted,
        "deleted_at": (
            post.deleted_at.isoformat()
            if post.deleted_at
            else None
        ),
    }


def comment_values(comment):
    return {
        "post": str(comment.post),
        "author": str(comment.author),
        "body": comment.body,
        "parent": (
            str(comment.parent)
            if comment.parent
            else None
        ),
    }


def save_post_with_targets(
    *,
    form,
    target_formset,
):
    with transaction.atomic():
        post = form.save()

        target_formset.instance = post

        if (
            post.visibility
            == Post.Visibility.SELECTED_GROUPS
        ):
            target_formset.save()
        else:
            post.targets.all().delete()

    return post


def create_post_targets_from_formset(
    *,
    post,
    target_formset,
):
    for target_form in target_formset.forms:
        if not hasattr(
            target_form,
            "cleaned_data",
        ):
            continue

        if target_form.cleaned_data.get(
            "DELETE"
        ):
            continue

        target_values = {
            field_name:
                target_form.cleaned_data.get(
                    field_name
                )
            for field_name
            in POST_TARGET_FIELDS
        }

        if not any(
            value is not None
            for value in target_values.values()
        ):
            continue

        PostTarget.objects.create(
            post=post,
            **target_values,
        )


def create_replacement_post(
    *,
    old_post,
    form,
    target_formset,
):
    with transaction.atomic():
        replacement_post = form.save()

        replacement_post.created_at = (
            old_post.created_at
        )

        replacement_post.save(
            update_fields=[
                "created_at",
            ]
        )

        if (
            replacement_post.visibility
            == Post.Visibility.SELECTED_GROUPS
        ):
            create_post_targets_from_formset(
                post=replacement_post,
                target_formset=target_formset,
            )

        Comment.objects.filter(
            post=old_post,
        ).update(
            post=replacement_post,
        )

        old_post.is_deleted = True
        old_post.deleted_at = timezone.now()

        old_post.save(
            update_fields=[
                "is_deleted",
                "deleted_at",
                "updated_at",
            ]
        )

    return replacement_post


def get_tavern_posts(user):
    if user.has_perm(
        "community.view_post"
    ):
        return (
            Post.objects
            .filter(
                is_deleted=False,
            )
            .select_related("author")
            .order_by("-created_at")
        )

    return get_visible_posts(
        user,
    )


@login_required
def post_list(request):
    composer_form = None
    target_formset = None

    if request.method == "POST":
        if not is_member(request.user):
            return HttpResponseForbidden()

        post = Post(
            author=request.user,
            visibility=Post.Visibility.MEMBERS,
        )

        composer_form = PostForm(
            request.POST,
            instance=post,
        )

        target_formset = PostTargetFormSet(
            request.POST,
            instance=post,
            prefix="targets",
        )

        composer_is_valid = (
            composer_form.is_valid()
        )

        target_formset_is_valid = (
            target_formset.is_valid()
        )

        if (
            composer_is_valid
            and target_formset_is_valid
        ):
            post = save_post_with_targets(
                form=composer_form,
                target_formset=target_formset,
            )

            record_audit_event(
                actor=request.user,
                request=request,
                action=AuditLog.Action.CREATE,
                target_type=(
                    post._meta.verbose_name
                ),
                target_id=post.pk,
                target_label=str(post),
                new_value=post_values(post),
                source=AuditLog.Source.WEB_APP,
                method=AuditLog.Method.MANUAL,
            )

            return redirect(
                "community:post_list",
            )

    elif is_member(request.user):
        post = Post(
            author=request.user,
            visibility=Post.Visibility.MEMBERS,
        )

        composer_form = PostForm(
            instance=post,
        )

        target_formset = PostTargetFormSet(
            instance=post,
            prefix="targets",
        )

    visible_posts = get_tavern_posts(
        request.user,
    )

    needs_attention_items = (
        get_needs_attention_items(
            request.user,
        )
    )

    return render(
        request,
        get_tavern_template(request),
        {
            "posts": visible_posts,
            "composer_form": composer_form,
            "target_formset": target_formset,
            "needs_attention_items":
                needs_attention_items,
        },
    )


def post_detail(request, post_id):
    post = get_object_or_404(
        Post.objects
        .filter(
            is_deleted=False,
        )
        .select_related("author")
        .prefetch_related(
            "targets",
            "comments__author",
            "comments__replies__author",
        ),
        pk=post_id,
    )

    if not can_view_post(
        request.user,
        post,
    ):
        return HttpResponseForbidden()

    comment_form = None
    reply_form = None

    if (
        is_member(request.user)
        and not post.is_locked
    ):
        comment_form = CommentForm()
        reply_form = ReplyForm()

    return render(
        request,
        "community/post_detail.html",
        {
            "post": post,
            "comment_form": comment_form,
            "reply_form": reply_form,
        },
    )


@login_required
def post_create(request):
    if not is_member(request.user):
        return HttpResponseForbidden()

    post = Post(
        author=request.user,
        visibility=Post.Visibility.MEMBERS,
    )

    if request.method == "POST":
        form = PostForm(
            request.POST,
            instance=post,
        )

        target_formset = PostTargetFormSet(
            request.POST,
            instance=post,
            prefix="targets",
        )

        form_is_valid = form.is_valid()
        formset_is_valid = (
            target_formset.is_valid()
        )

        if (
            form_is_valid
            and formset_is_valid
        ):
            post = save_post_with_targets(
                form=form,
                target_formset=target_formset,
            )

            record_audit_event(
                actor=request.user,
                request=request,
                action=AuditLog.Action.CREATE,
                target_type=(
                    post._meta.verbose_name
                ),
                target_id=post.pk,
                target_label=str(post),
                new_value=post_values(post),
                source=AuditLog.Source.WEB_APP,
                method=AuditLog.Method.MANUAL,
            )

            return redirect(
                "community:post_detail",
                post_id=post.pk,
            )

    else:
        form = PostForm(
            instance=post,
        )

        target_formset = PostTargetFormSet(
            instance=post,
            prefix="targets",
        )

    return render(
        request,
        "community/post_form.html",
        {
            "form": form,
            "target_formset": target_formset,
            "page_title": "Create Post",
        },
    )


@login_required
def post_edit(request, post_id):
    post = get_object_or_404(
        Post.objects
        .filter(
            is_deleted=False,
        )
        .prefetch_related(
            "targets",
        ),
        pk=post_id,
    )

    if not can_edit_post(
        request.user,
        post,
    ):
        return HttpResponseForbidden()

    old_value = post_values(post)

    if request.method == "POST":
        replacement_post = Post(
            author=post.author,
            visibility=post.visibility,
            is_official=post.is_official,
            is_pinned=post.is_pinned,
            is_locked=post.is_locked,
            previous_version=post,
        )

        form = PostForm(
            request.POST,
            instance=replacement_post,
        )

        target_formset = PostTargetFormSet(
            request.POST,
            instance=post,
            prefix="targets",
        )

        form_is_valid = form.is_valid()

        original_visibility = (
            post.visibility
        )

        if form_is_valid:
            post.visibility = (
                form.cleaned_data[
                    "visibility"
                ]
            )

        formset_is_valid = (
            target_formset.is_valid()
        )

        post.visibility = original_visibility

        if (
            form_is_valid
            and formset_is_valid
        ):
            replacement_post = (
                create_replacement_post(
                    old_post=post,
                    form=form,
                    target_formset=target_formset,
                )
            )

            record_audit_event(
                actor=request.user,
                request=request,
                action=AuditLog.Action.UPDATE,
                target_type=(
                    post._meta.verbose_name
                ),
                target_id=post.pk,
                target_label=str(post),
                old_value=old_value,
                new_value=post_values(
                    replacement_post,
                ),
                source=AuditLog.Source.WEB_APP,
                method=AuditLog.Method.MANUAL,
            )

            return redirect(
                "community:post_detail",
                post_id=replacement_post.pk,
            )

    else:
        form = PostForm(
            instance=post,
        )

        target_formset = PostTargetFormSet(
            instance=post,
            prefix="targets",
        )

    return render(
        request,
        "community/post_form.html",
        {
            "form": form,
            "target_formset": target_formset,
            "post": post,
            "page_title": "Edit Post",
        },
    )


@login_required
def post_delete(request, post_id):
    post = get_object_or_404(
        Post.objects
        .filter(
            is_deleted=False,
        )
        .prefetch_related(
            "targets",
        ),
        pk=post_id,
    )

    if not can_delete_post(
        request.user,
        post,
    ):
        return HttpResponseForbidden()

    if request.method == "POST":
        old_value = post_values(post)

        post.is_deleted = True
        post.deleted_at = timezone.now()

        post.save(
            update_fields=[
                "is_deleted",
                "deleted_at",
                "updated_at",
            ]
        )

        record_audit_event(
            actor=request.user,
            request=request,
            action=AuditLog.Action.DELETE,
            target_type=(
                post._meta.verbose_name
            ),
            target_id=post.pk,
            target_label=str(post),
            old_value=old_value,
            new_value=post_values(post),
            source=AuditLog.Source.WEB_APP,
            method=AuditLog.Method.MANUAL,
        )

        return redirect(
            "community:post_list",
        )

    return render(
        request,
        "community/confirm_delete.html",
        {
            "object_type": "post",
            "body": post.body,
            "cancel_url":
                "community:post_detail",
            "cancel_id": post.id,
        },
    )


@login_required
@require_POST
def add_comment(request, post_id):
    if not is_member(request.user):
        return HttpResponseForbidden()

    post = get_object_or_404(
        Post.objects.filter(
            is_deleted=False,
        ),
        pk=post_id,
    )

    if not can_view_post(
        request.user,
        post,
    ):
        return HttpResponseForbidden()

    if post.is_locked:
        return HttpResponseForbidden()

    form = CommentForm(
        request.POST,
    )

    if form.is_valid():
        comment = form.save(
            commit=False,
        )

        comment.post = post
        comment.author = request.user
        comment.save()

        record_audit_event(
            actor=request.user,
            request=request,
            action=AuditLog.Action.CREATE,
            target_type=(
                comment._meta.verbose_name
            ),
            target_id=comment.pk,
            target_label=str(comment),
            new_value=comment_values(
                comment,
            ),
            source=AuditLog.Source.WEB_APP,
            method=AuditLog.Method.MANUAL,
        )

    return redirect(
        "community:post_detail",
        post_id=post.pk,
    )


@login_required
@require_POST
def add_reply(request, comment_id):
    if not is_member(request.user):
        return HttpResponseForbidden()

    parent = get_object_or_404(
        Comment.objects.select_related(
            "post",
        ),
        pk=comment_id,
    )

    post = parent.post

    if not can_view_post(
        request.user,
        post,
    ):
        return HttpResponseForbidden()

    if post.is_locked:
        return HttpResponseForbidden()

    if parent.parent_id is not None:
        return HttpResponseForbidden()

    form = ReplyForm(
        request.POST,
    )

    if form.is_valid():
        reply = form.save(
            commit=False,
        )

        reply.post = post
        reply.author = request.user
        reply.parent = parent

        reply.full_clean()
        reply.save()

        record_audit_event(
            actor=request.user,
            request=request,
            action=AuditLog.Action.CREATE,
            target_type=(
                reply._meta.verbose_name
            ),
            target_id=reply.pk,
            target_label=str(reply),
            new_value=comment_values(
                reply,
            ),
            source=AuditLog.Source.WEB_APP,
            method=AuditLog.Method.MANUAL,
        )

    return redirect(
        "community:post_detail",
        post_id=post.pk,
    )


@login_required
@require_POST
def comment_edit(request, comment_id):
    comment = get_object_or_404(
        Comment.objects.select_related(
            "post",
        ),
        pk=comment_id,
    )

    if not can_edit_comment(
        request.user,
        comment,
    ):
        return HttpResponseForbidden()

    if comment.post.is_locked:
        return HttpResponseForbidden()

    old_value = comment_values(
        comment,
    )

    form = CommentForm(
        request.POST,
        instance=comment,
    )

    if form.is_valid():
        comment = form.save()

        record_audit_event(
            actor=request.user,
            request=request,
            action=AuditLog.Action.UPDATE,
            target_type=(
                comment._meta.verbose_name
            ),
            target_id=comment.pk,
            target_label=str(comment),
            old_value=old_value,
            new_value=comment_values(
                comment,
            ),
            source=AuditLog.Source.WEB_APP,
            method=AuditLog.Method.MANUAL,
        )

    return redirect(
        "community:post_detail",
        post_id=comment.post_id,
    )


@login_required
def comment_delete(request, comment_id):
    comment = get_object_or_404(
        Comment.objects.select_related(
            "post",
        ),
        pk=comment_id,
    )

    if not can_delete_comment(
        request.user,
        comment,
    ):
        return HttpResponseForbidden()

    post_id = comment.post_id

    if request.method == "POST":
        old_value = comment_values(
            comment,
        )

        target_id = comment.pk
        target_label = str(comment)
        target_type = (
            comment._meta.verbose_name
        )

        comment.delete()

        record_audit_event(
            actor=request.user,
            request=request,
            action=AuditLog.Action.DELETE,
            target_type=target_type,
            target_id=target_id,
            target_label=target_label,
            old_value=old_value,
            source=AuditLog.Source.WEB_APP,
            method=AuditLog.Method.MANUAL,
        )

        return redirect(
            "community:post_detail",
            post_id=post_id,
        )

    return render(
        request,
        "community/confirm_delete.html",
        {
            "object_type": "comment",
            "body": comment.body,
            "cancel_url":
                "community:post_detail",
            "cancel_id": post_id,
        },
    )