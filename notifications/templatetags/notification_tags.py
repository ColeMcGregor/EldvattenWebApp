from django import template

from notifications.services import (
    get_unread_notification_count,
)


register = template.Library()


@register.simple_tag(takes_context=True)
def unread_notification_count(context):
    request = context.get("request")

    if request is None:
        return 0

    if not request.user.is_authenticated:
        return 0

    return get_unread_notification_count(
        request.user,
    )