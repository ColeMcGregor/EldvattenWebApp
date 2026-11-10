
from django.urls import path

from . import views


app_name = "feedback"

urlpatterns = [
    path(
        "report/",
        views.report_bug,
        name="report_bug",
    ),
    path(
        "received/",
        views.report_received,
        name="report_received",
    ),
]
