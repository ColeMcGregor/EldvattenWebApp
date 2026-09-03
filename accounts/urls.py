from django.urls import path

from . import views


urlpatterns = [
    path(
        "register/",
        views.register,
        name="register",
    ),
    path(
        "notification-setup/",
        views.notification_setup,
        name="notification_setup",
    ),
    path(
        "my-eldvatten/",
        views.my_eldvatten,
        name="my_eldvatten",
    ),
    path(
        "login/",
        views.user_login,
        name="login",
    ),
    path(
        "logout/",
        views.user_logout,
        name="logout",
    ),
]