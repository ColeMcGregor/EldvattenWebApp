from django.urls import path

from . import views


app_name = "actions"


urlpatterns = [
    path(
        "",
        views.action_list,
        name="list",
    ),
    path(
        "create/",
        views.action_create,
        name="create",
    ),
    path(
        "manage/",
        views.action_manage_list,
        name="manage_list",
    ),
    path(
        "manage/<int:action_id>/",
        views.action_manage_detail,
        name="manage_detail",
    ),
    path(
        "manage/<int:action_id>/edit/",
        views.action_edit,
        name="edit",
    ),
    path(
        "manage/<int:action_id>/delete/",
        views.action_delete,
        name="delete",
    ),
    path(
        "manage/<int:action_id>/sync/",
        views.action_resolve_assignments,
        name="sync_assignments",
    ),
    path(
        "<int:action_id>/",
        views.action_detail,
        name="detail",
    ),
    path(
        "<int:action_id>/complete/",
        views.action_complete,
        name="complete",
    ),
]