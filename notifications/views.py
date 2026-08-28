import json
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .models import (
    Notification,
    PushSubscription,
)
from .services import (
    get_unread_notification_count,
    get_user_notifications,
    mark_all_notifications_read,
    mark_notification_read,
    mark_notification_unread,
)


@login_required
def notification_list(request):
    notifications = get_user_notifications(
        request.user,
    )

    unread_count = get_unread_notification_count(
        request.user,
    )

    return render(
        request,
        "notifications/notification_list.html",
        {
            "notifications": notifications,
            "unread_count": unread_count,
        },
    )


@login_required
def notification_open(request, notification_id):
    notification = get_object_or_404(
        Notification,
        id=notification_id,
        user=request.user,
    )

    mark_notification_read(
        notification,
    )

    if notification.target_url:
        return redirect(
            notification.target_url,
        )

    return redirect(
        "notifications:notification_list",
    )


@login_required
def notification_mark_read(
    request,
    notification_id,
):
    if request.method != "POST":
        return redirect(
            "notifications:notification_list",
        )

    notification = get_object_or_404(
        Notification,
        id=notification_id,
        user=request.user,
    )

    mark_notification_read(
        notification,
    )

    return redirect(
        "notifications:notification_list",
    )


@login_required
def notification_mark_unread(
    request,
    notification_id,
):
    if request.method != "POST":
        return redirect(
            "notifications:notification_list",
        )

    notification = get_object_or_404(
        Notification,
        id=notification_id,
        user=request.user,
    )

    mark_notification_unread(
        notification,
    )

    return redirect(
        "notifications:notification_list",
    )


@login_required
def notification_mark_all_read(request):
    if request.method != "POST":
        return redirect(
            "notifications:notification_list",
        )

    updated_count = mark_all_notifications_read(
        request.user,
    )

    if updated_count:
        messages.success(
            request,
            f"Marked {updated_count} notification(s) as read.",
        )

    return redirect(
        "notifications:notification_list",
    )


@login_required
@require_GET
def push_public_key(request):
    return JsonResponse(
        {
            "public_key": settings.VAPID_PUBLIC_KEY,
        },
    )


@login_required
@require_POST
def push_subscribe(request):
    try:
        data = json.loads(
            request.body,
        )
    except json.JSONDecodeError:
        return JsonResponse(
            {
                "success": False,
                "error": "Invalid request data.",
            },
            status=400,
        )

    endpoint = data.get("endpoint")

    keys = data.get(
        "keys",
        {},
    )

    p256dh_key = keys.get("p256dh")
    auth_key = keys.get("auth")

    device_name = data.get(
        "device_name",
        "",
    )

    if not endpoint or not p256dh_key or not auth_key:
        return JsonResponse(
            {
                "success": False,
                "error": "Push subscription data is incomplete.",
            },
            status=400,
        )

    subscription, created = (
        PushSubscription.objects.update_or_create(
            endpoint=endpoint,
            defaults={
                "user": request.user,
                "p256dh_key": p256dh_key,
                "auth_key": auth_key,
                "device_name": device_name,
                "active": True,
                "paused_until": None,
            },
        )
    )

    if not request.user.push_prompt_seen:
        request.user.push_prompt_seen = True

        request.user.save(
            update_fields=[
                "push_prompt_seen",
            ],
        )

    return JsonResponse(
        {
            "success": True,
            "created": created,
            "subscription_id": subscription.id,
        },
    )


@login_required
@require_POST
def push_status(request):
    try:
        data = json.loads(
            request.body,
        )
    except json.JSONDecodeError:
        return JsonResponse(
            {
                "success": False,
                "error": "Invalid request data.",
            },
            status=400,
        )

    endpoint = data.get("endpoint")

    if not endpoint:
        return JsonResponse(
            {
                "success": True,
                "registered": False,
            },
        )

    subscription = (
        PushSubscription.objects.filter(
            user=request.user,
            endpoint=endpoint,
        )
        .first()
    )

    if subscription is None:
        return JsonResponse(
            {
                "success": True,
                "registered": False,
            },
        )

    is_paused = (
        subscription.paused_until is not None
        and subscription.paused_until > timezone.now()
    )

    return JsonResponse(
        {
            "success": True,
            "registered": True,
            "active": subscription.active,
            "paused": is_paused,
            "paused_until": subscription.paused_until,
        },
    )


@login_required
@require_POST
def push_set_active(request):
    try:
        data = json.loads(
            request.body,
        )
    except json.JSONDecodeError:
        return JsonResponse(
            {
                "success": False,
                "error": "Invalid request data.",
            },
            status=400,
        )

    endpoint = data.get("endpoint")
    active = data.get("active")

    if not endpoint or not isinstance(active, bool):
        return JsonResponse(
            {
                "success": False,
                "error": "Endpoint and active state are required.",
            },
            status=400,
        )

    subscription = get_object_or_404(
        PushSubscription,
        user=request.user,
        endpoint=endpoint,
    )

    subscription.active = active

    subscription.save(
        update_fields=[
            "active",
            "updated_at",
        ],
    )

    return JsonResponse(
        {
            "success": True,
            "active": subscription.active,
        },
    )


@login_required
@require_POST
def push_pause(request):
    try:
        data = json.loads(
            request.body,
        )
    except json.JSONDecodeError:
        return JsonResponse(
            {
                "success": False,
                "error": "Invalid request data.",
            },
            status=400,
        )

    endpoint = data.get("endpoint")
    hours = data.get("hours")

    if not endpoint:
        return JsonResponse(
            {
                "success": False,
                "error": "Push subscription endpoint is required.",
            },
            status=400,
        )

    if not isinstance(hours, int) or not 1 <= hours <= 24:
        return JsonResponse(
            {
                "success": False,
                "error": "Pause must be between 1 and 24 hours.",
            },
            status=400,
        )

    subscription = get_object_or_404(
        PushSubscription,
        user=request.user,
        endpoint=endpoint,
    )

    subscription.paused_until = (
        timezone.now()
        + timedelta(
            hours=hours,
        )
    )

    subscription.save(
        update_fields=[
            "paused_until",
            "updated_at",
        ],
    )

    return JsonResponse(
        {
            "success": True,
            "paused_until": subscription.paused_until,
        },
    )


@login_required
@require_POST
def push_reset_pause(request):
    try:
        data = json.loads(
            request.body,
        )
    except json.JSONDecodeError:
        return JsonResponse(
            {
                "success": False,
                "error": "Invalid request data.",
            },
            status=400,
        )

    endpoint = data.get("endpoint")

    if not endpoint:
        return JsonResponse(
            {
                "success": False,
                "error": "Push subscription endpoint is required.",
            },
            status=400,
        )

    subscription = get_object_or_404(
        PushSubscription,
        user=request.user,
        endpoint=endpoint,
    )

    subscription.paused_until = None

    subscription.save(
        update_fields=[
            "paused_until",
            "updated_at",
        ],
    )

    return JsonResponse(
        {
            "success": True,
        },
    )