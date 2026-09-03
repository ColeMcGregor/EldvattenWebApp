from django.urls import path

from . import views


app_name = "resources"


urlpatterns = [
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