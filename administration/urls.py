
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
        "accounts/members/",
        views.account_list,
        name="account_list",
    ),
    path(
        "accounts/members/<int:user_id>/",
        views.account_detail,
        name="account_detail",
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
        "system/bug-reports/",
        views.bug_report_list,
        name="bug_report_list",
    ),
    path(
        "system/bug-reports/<int:report_id>/",
        views.bug_report_detail,
        name="bug_report_detail",
    ),
    path(
        "<slug:section_slug>/",
        views.administration_section,
        name="section",
    ),
]
