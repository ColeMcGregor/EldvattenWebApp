from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.models import AccountStatus
from audit.models import AuditLog
from audit.services import record_audit_event
from organization.models import GroupMembership

from .forms import CommentForm, PostForm, ReplyForm
from .models import Comment, Post


def is_member(user):
    return (
        user.is_authenticated
        and user.is_active
        and user.account_status == AccountStatus.MEMBER
    )


def is_guest(user):
    return (
        user.is_authenticated
        and user.is_active
        and user.account_status == AccountStatus.PENDING
    )


def get_user_group_ids(user):
    if not is_member(user):
        return []

    return list(
        GroupMembership.objects.filter(
            user=user,
            ended_at__isnull=True,
        ).values_list(
            "community_group_id",
            flat=True,
        )
    )


def can_view_post(user, post):
    if post.visibility == Post.Visibility.PUBLIC:
        return True

    if (
        user.is_authenticated
        and user.has_perm("community.view_post")
    ):
        return True

    if post.visibility == Post.Visibility.GUESTS:
        return is_guest(user) or is_member(user)

    if post.visibility == Post.Visibility.MEMBERS:
        return is_member(user)

    if post.visibility == Post.Visibility.SELECTED_GROUPS:
        if not is_member(user):
            return False

        user_group_ids = get_user_group_ids(user)

        return post.visible_to_groups.filter(
            id__in=user_group_ids,
        ).exists()

    return False


def can_edit_post(user, post):
    if not is_member(user):
        return False

    return (
        post.author_id == user.id
        or user.has_perm("community.change_post")
    )


def can_delete_post(user, post):
    if not is_member(user):
        return False

    return (
        post.author_id == user.id
        or user.has_perm("community.delete_post")
    )


def can_edit_comment(user, comment):
    if not is_member(user):
        return False

    return (
        comment.author_id == user.id
        or user.has_perm("community.change_comment")
    )


def can_delete_comment(user, comment):
    if not is_member(user):
        return False

    return (
        comment.author_id == user.id
        or user.has_perm("community.delete_comment")
    )


def post_values(post):
    return {
        "author": str(post.author),
        "body": post.body,
        "visibility": post.visibility,
        "visible_to_groups": list(
            post.visible_to_groups.values_list(
                "name",
                flat=True,
            )
        ),
        "is_official": post.is_official,
        "is_pinned": post.is_pinned,
        "is_locked": post.is_locked,
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


def post_list(request):
    posts = Post.objects.select_related(
        "author",
    ).prefetch_related(
        "visible_to_groups",
    )

    if (
        request.user.is_authenticated
        and request.user.has_perm("community.view_post")
    ):
        visible_posts = posts

    elif is_member(request.user):
        user_group_ids = get_user_group_ids(request.user)

        visible_posts = [
            post
            for post in posts
            if (
                post.visibility
                in {
                    Post.Visibility.PUBLIC,
                    Post.Visibility.GUESTS,
                    Post.Visibility.MEMBERS,
                }
                or (
                    post.visibility
                    == Post.Visibility.SELECTED_GROUPS
                    and post.visible_to_groups.filter(
                        id__in=user_group_ids,
                    ).exists()
                )
            )
        ]

    elif is_guest(request.user):
        visible_posts = posts.filter(
            visibility__in=[
                Post.Visibility.PUBLIC,
                Post.Visibility.GUESTS,
            ]
        )

    else:
        visible_posts = posts.filter(
            visibility=Post.Visibility.PUBLIC
        )

    return render(
        request,
        "community/post_list.html",
        {
            "posts": visible_posts,
        },
    )


def post_detail(request, post_id):
    post = get_object_or_404(
        Post.objects.select_related(
            "author",
        ).prefetch_related(
            "visible_to_groups",
            "comments__author",
            "comments__replies__author",
        ),
        pk=post_id,
    )

    if not can_view_post(request.user, post):
        return HttpResponseForbidden()

    comment_form = None
    reply_form = None

    if is_member(request.user) and not post.is_locked:
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

    if request.method == "POST":
        form = PostForm(request.POST)

        if form.is_valid():
            post = form.save(commit=False)
            post.author = request.user
            post.save()
            form.save_m2m()

            record_audit_event(
                actor=request.user,
                request=request,
                action=AuditLog.Action.CREATE,
                target_type=post._meta.verbose_name,
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
        form = PostForm()

    return render(
        request,
        "community/post_form.html",
        {
            "form": form,
            "page_title": "Create Post",
        },
    )


@login_required
def post_edit(request, post_id):
    post = get_object_or_404(Post, pk=post_id)

    if not can_edit_post(request.user, post):
        return HttpResponseForbidden()

    old_value = post_values(post)

    if request.method == "POST":
        form = PostForm(
            request.POST,
            instance=post,
        )

        if form.is_valid():
            post = form.save()

            record_audit_event(
                actor=request.user,
                request=request,
                action=AuditLog.Action.UPDATE,
                target_type=post._meta.verbose_name,
                target_id=post.pk,
                target_label=str(post),
                old_value=old_value,
                new_value=post_values(post),
                source=AuditLog.Source.WEB_APP,
                method=AuditLog.Method.MANUAL,
            )

            return redirect(
                "community:post_detail",
                post_id=post.pk,
            )
    else:
        form = PostForm(instance=post)

    return render(
        request,
        "community/post_form.html",
        {
            "form": form,
            "post": post,
            "page_title": "Edit Post",
        },
    )


@login_required
def post_delete(request, post_id):
    post = get_object_or_404(Post, pk=post_id)

    if not can_delete_post(request.user, post):
        return HttpResponseForbidden()

    if request.method == "POST":
        old_value = post_values(post)
        target_id = post.pk
        target_label = str(post)
        target_type = post._meta.verbose_name

        post.delete()

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

        return redirect("community:post_list")

    return render(
        request,
        "community/confirm_delete.html",
        {
            "object_type": "post",
            "body": post.body,
            "cancel_url": "community:post_detail",
            "cancel_id": post.id,
        },
    )


@login_required
@require_POST
def add_comment(request, post_id):
    if not is_member(request.user):
        return HttpResponseForbidden()

    post = get_object_or_404(Post, pk=post_id)

    if not can_view_post(request.user, post):
        return HttpResponseForbidden()

    if post.is_locked:
        return HttpResponseForbidden()

    form = CommentForm(request.POST)

    if form.is_valid():
        comment = form.save(commit=False)
        comment.post = post
        comment.author = request.user
        comment.save()

        record_audit_event(
            actor=request.user,
            request=request,
            action=AuditLog.Action.CREATE,
            target_type=comment._meta.verbose_name,
            target_id=comment.pk,
            target_label=str(comment),
            new_value=comment_values(comment),
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
        Comment.objects.select_related("post"),
        pk=comment_id,
    )

    post = parent.post

    if not can_view_post(request.user, post):
        return HttpResponseForbidden()

    if post.is_locked:
        return HttpResponseForbidden()

    if parent.parent_id is not None:
        return HttpResponseForbidden()

    form = ReplyForm(request.POST)

    if form.is_valid():
        reply = form.save(commit=False)
        reply.post = post
        reply.author = request.user
        reply.parent = parent
        reply.full_clean()
        reply.save()

        record_audit_event(
            actor=request.user,
            request=request,
            action=AuditLog.Action.CREATE,
            target_type=reply._meta.verbose_name,
            target_id=reply.pk,
            target_label=str(reply),
            new_value=comment_values(reply),
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
        Comment.objects.select_related("post"),
        pk=comment_id,
    )

    if not can_edit_comment(request.user, comment):
        return HttpResponseForbidden()

    if comment.post.is_locked:
        return HttpResponseForbidden()

    old_value = comment_values(comment)

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
            target_type=comment._meta.verbose_name,
            target_id=comment.pk,
            target_label=str(comment),
            old_value=old_value,
            new_value=comment_values(comment),
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
        Comment.objects.select_related("post"),
        pk=comment_id,
    )

    if not can_delete_comment(request.user, comment):
        return HttpResponseForbidden()

    post_id = comment.post_id

    if request.method == "POST":
        old_value = comment_values(comment)
        target_id = comment.pk
        target_label = str(comment)
        target_type = comment._meta.verbose_name

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
            "cancel_url": "community:post_detail",
            "cancel_id": post_id,
        },
    )