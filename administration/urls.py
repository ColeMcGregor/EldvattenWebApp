
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
        "system/logs/",
        views.audit_log_list,
        name="audit_log_list",
    ),
    path(
        "system/logs/<int:log_id>/",
        views.audit_log_detail,
        name="audit_log_detail",
    ),
    path(
        "<slug:section_slug>/",
        views.administration_section,
        name="section",
    ),
]
