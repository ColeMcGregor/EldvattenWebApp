"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.conf import settings
from django.contrib import admin
from django.http import FileResponse
from django.urls import include, path


def service_worker(request):
    service_worker_path = (
        settings.BASE_DIR
        / "static"
        / "js"
        / "notifications"
        / "service-worker.js"
    )

    response = FileResponse(
        open(service_worker_path, "rb"),
        content_type="application/javascript",
    )

    response["Cache-Control"] = "no-cache"

    return response


urlpatterns = [
    path("service-worker.js", service_worker, name="service_worker"),
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("actions/", include("actions.urls")),
    path("events/", include("events.urls")),
    path("community/", include("community.urls")),
    path("messages/", include("messaging.urls")),
    path("votes/", include("voting.urls")),
    path("notifications/", include("notifications.urls")),
    path("", include("core.urls")),
]