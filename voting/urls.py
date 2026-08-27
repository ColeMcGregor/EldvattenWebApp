from django.urls import path

from . import views


app_name = "voting"


urlpatterns = [
    path(
        "",
        views.vote_list,
        name="vote_list",
    ),
    path(
        "manage/",
        views.vote_manage_list,
        name="vote_manage_list",
    ),
    path(
        "manage/create/",
        views.vote_create,
        name="vote_create",
    ),
    path(
        "manage/<int:vote_id>/",
        views.vote_manage_detail,
        name="vote_manage_detail",
    ),
    path(
        "manage/<int:vote_id>/edit/",
        views.vote_edit,
        name="vote_edit",
    ),
    path(
        "manage/<int:vote_id>/open/",
        views.vote_open,
        name="vote_open",
    ),
    path(
        "manage/<int:vote_id>/close/",
        views.vote_close,
        name="vote_close",
    ),
    path(
        "manage/<int:vote_id>/delete/",
        views.vote_delete,
        name="vote_delete",
    ),
    path(
        "<int:vote_id>/",
        views.vote_detail,
        name="vote_detail",
    ),
    path(
        "<int:vote_id>/submit/",
        views.vote_submit,
        name="vote_submit",
    ),
]