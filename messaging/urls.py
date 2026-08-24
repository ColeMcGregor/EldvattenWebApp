from django.urls import path

from . import views


app_name = "messaging"


urlpatterns = [
    path(
        "",
        views.conversation_list,
        name="conversation_list",
    ),
    path(
        "create/",
        views.conversation_create,
        name="conversation_create",
    ),
    path(
        "<int:conversation_id>/",
        views.conversation_detail,
        name="conversation_detail",
    ),
    path(
        "<int:conversation_id>/send/",
        views.send_message,
        name="send_message",
    ),
    path(
        "<int:conversation_id>/leave/",
        views.leave_conversation,
        name="leave_conversation",
    ),
    path(
        "block/<int:user_id>/",
        views.block_user,
        name="block_user",
    ),
    path(
        "unblock/<int:user_id>/",
        views.unblock_user,
        name="unblock_user",
    ),
]