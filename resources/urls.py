
from django.urls import path

from . import views


app_name = "resources"


urlpatterns = [
    path(
        "",
        views.resource_list,
        name="list",
    ),
    path(
        "manage/",
        views.manage_resources,
        name="manage_list",
    ),
    path(
        "manage/create/",
        views.create_resource,
        name="create",
    ),
    path(
        "manage/<int:resource_id>/",
        views.manage_resource_detail,
        name="manage_detail",
    ),
    path(
        "manage/<int:resource_id>/edit/",
        views.edit_resource,
        name="edit",
    ),
    path(
        "<int:resource_id>/download/",
        views.download_resource,
        name="download",
    ),
    path(
        "<int:resource_id>/open/",
        views.open_resource,
        name="open",
    ),
]
