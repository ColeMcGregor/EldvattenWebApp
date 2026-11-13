from django.urls import path

from . import views


app_name = "organization"


urlpatterns = [
    path("", views.organization_index, name="index"),
    path("chapters/", views.chapter_manage, name="chapter_manage"),
    path("chapters/<int:chapter_id>/", views.chapter_detail, name="chapter_detail"),
    path("households/", views.household_manage, name="household_manage"),
    path("households/<int:household_id>/", views.household_detail, name="household_detail"),
    path("citizenship/", views.citizenship_manage, name="citizenship_manage"),
    path("ranks/", views.social_rank_manage, name="social_rank_manage"),
    path("offices/", views.office_manage, name="office_manage"),
    path("governance/", views.governance_manage, name="governance_manage"),
    path("governance/<int:body_id>/", views.governance_detail, name="governance_detail"),
    path("orders/", views.order_manage, name="order_manage"),
    path("orders/ranks/", views.order_rank_manage, name="order_rank_manage"),
    path("orders/<int:order_id>/", views.order_detail, name="order_detail"),
    path("groups/", views.community_group_manage, name="community_group_manage"),
    path("groups/<int:group_id>/", views.community_group_detail, name="community_group_detail"),
]
