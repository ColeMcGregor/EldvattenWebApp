
from django.urls import path

from . import views


app_name = "administration"


urlpatterns = [
    path(
        "",
        views.administration_index,
        name="index",
    ),
    path(
        "<slug:section_slug>/",
        views.administration_section,
        name="section",
    ),
]
