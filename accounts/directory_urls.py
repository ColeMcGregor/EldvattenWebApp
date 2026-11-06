from django.urls import path

from .directory_views import directory_index


app_name = "directory"

urlpatterns = [
    path("", directory_index, name="index"),
]
