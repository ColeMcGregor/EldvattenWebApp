from django.urls import path

from . import views


urlpatterns = [
    path("", views.home, name="home"),
    path("about/", views.about, name="about"),
    path("calendar/", views.calendar_view, name="calendar"),
    path("tavern/", views.tavern, name="tavern"),
    path("contact/", views.contact, name="contact"),
    path("privacy/", views.privacy, name="privacy"),
]