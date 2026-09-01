import json

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from pywebpush import WebPushException, webpush

from .models import (
    Notification,
    NotificationPreference,
    PushSubscription,
)


def user_allows_push(
    *,
    user_id,
    notification_type,
    preferences,
):
    preference = preferences.get(user_id)

    if preference is None:
        return True

    return preference.allows_push(
        notification_type,
    )


@transaction.atomic
def create_notifications(
    *,
    recipients,
    notification_type,
    title,
    message="",
    source_type="",
    source_id="",
    target_url="",
):
    recipient_ids = set()

    for recipient in recipients:
        if recipient is None:
            continue

        if not getattr(recipient, "pk", None):
            continue

        recipient_ids.add(recipient.pk)

    if not recipient_ids:
        return []

    preferences = {
        preference.user_id: preference
        for preference in NotificationPreference.objects.filter(
            user_id__in=recipient_ids,
        )
    }

    notifications = [
        Notification(
            user_id=user_id,
            notification_type=notification_type,
            title=title,
            message=message,
            source_type=source_type,
            source_id=(
                str(source_id)
                if source_id is not None
                else ""
            ),
            target_url=target_url,
            push_requested=user_allows_push(
                user_id=user_id,
                notification_type=notification_type,
                preferences=preferences,
            ),
        )
        for user_id in recipient_ids
    ]

    created_notifications = (
        Notification.objects.bulk_create(
            notifications,
        )
    )

    push_notifications = [
        notification
        for notification in created_notifications
        if notification.push_requested
    ]

    if push_notifications:
        transaction.on_commit(
            lambda: send_push_notifications(
                push_notifications
            )
        )

    return created_notifications


def send_push_notifications(notifications):
    for notification in notifications:
        send_push_notification(
            notification,
        )


def send_push_notification(notification):
    now = timezone.now()

    subscriptions = PushSubscription.objects.filter(
        user_id=notification.user_id,
        enabled=True,
        active=True,
    ).filter(
        Q(paused_until__isnull=True)
        | Q(paused_until__lte=now)
    )

    payload = json.dumps(
        {
            "title": notification.title,
            "message": notification.message,
            "target_url": (
                notification.target_url
                or "/notifications/"
            ),
        }
    )

    for subscription in subscriptions:
        send_push_to_subscription(
            subscription=subscription,
            payload=payload,
        )


def send_push_to_subscription(
    *,
    subscription,
    payload,
):
    try:
        webpush(
            subscription_info={
                "endpoint": subscription.endpoint,
                "keys": {
                    "p256dh":
                        subscription.p256dh_key,
                    "auth":
                        subscription.auth_key,
                },
            },
            data=payload,
            vapid_private_key=(
                settings.VAPID_PRIVATE_KEY
            ),
            vapid_claims={
                "sub": settings.VAPID_SUBJECT,
            },
        )

    except WebPushException as error:
        response = error.response

        if (
            response is not None
            and response.status_code in {
                404,
                410,
            }
        ):
            subscription.active = False

            subscription.save(
                update_fields=[
                    "active",
                    "updated_at",
                ]
            )


@transaction.atomic
def mark_notification_read(notification):
    if notification.is_read:
        return notification

    notification.is_read = True
    notification.read_at = timezone.now()

    notification.save(
        update_fields=[
            "is_read",
            "read_at",
        ]
    )

    return notification


@transaction.atomic
def mark_notification_unread(notification):
    if not notification.is_read:
        return notification

    notification.is_read = False
    notification.read_at = None

    notification.save(
        update_fields=[
            "is_read",
            "read_at",
        ]
    )

    return notification


@transaction.atomic
def mark_all_notifications_read(user):
    now = timezone.now()

    return Notification.objects.filter(
        user=user,
        is_read=False,
    ).update(
        is_read=True,
        read_at=now,
    )


def get_unread_notification_count(user):
    return Notification.objects.filter(
        user=user,
        is_read=False,
    ).count()


def get_user_notifications(user):
    return Notification.objects.filter(
        user=user,
    ).order_by(
        "-created_at",
    )


def get_unread_notifications(user):
    return Notification.objects.filter(
        user=user,
        is_read=False,
    ).order_by(
        "-created_at",
    )