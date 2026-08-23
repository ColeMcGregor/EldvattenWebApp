from django.urls import path

from . import views


app_name = "community"


urlpatterns = [
    path("", views.post_list, name="post_list"),
    path("create/", views.post_create, name="post_create"),
    path("<int:post_id>/", views.post_detail, name="post_detail"),
    path("<int:post_id>/edit/", views.post_edit, name="post_edit"),
    path("<int:post_id>/delete/", views.post_delete, name="post_delete"),
    path(
        "<int:post_id>/comment/",
        views.add_comment,
        name="add_comment",
    ),
    path(
        "comments/<int:comment_id>/reply/",
        views.add_reply,
        name="add_reply",
    ),
    path(
        "comments/<int:comment_id>/edit/",
        views.comment_edit,
        name="comment_edit",
    ),
    path(
        "comments/<int:comment_id>/delete/",
        views.comment_delete,
        name="comment_delete",
    ),
]