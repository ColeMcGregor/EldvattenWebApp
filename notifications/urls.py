from django.urls import path

from . import views


app_name = "notifications"


urlpatterns = [
    path("", views.notification_list, name="notification_list"),
    path("<int:notification_id>/open/", views.notification_open, name="notification_open"),
    path("<int:notification_id>/read/", views.notification_mark_read, name="notification_mark_read"),
    path("<int:notification_id>/unread/", views.notification_mark_unread, name="notification_mark_unread"),
    path("read-all/", views.notification_mark_all_read, name="notification_mark_all_read"),
    path("push/public-key/", views.push_public_key, name="push_public_key"),
    path("push/subscribe/", views.push_subscribe, name="push_subscribe"),
    path("push/status/", views.push_status, name="push_status"),
    path("push/active/", views.push_set_active, name="push_set_active"),
    path("push/pause/", views.push_pause, name="push_pause"),
    path("push/pause/reset/", views.push_reset_pause, name="push_reset_pause"),
]