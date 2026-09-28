from django.urls import path

from . import views

app_name = "disputes"
urlpatterns = [
    path(
        "brand/campaigns/<int:campaign_id>/creators/<int:slot_id>/report/",
        views.brand_report,
        name="brand_report",
    ),
    path("creator/campaigns/<int:slot_id>/report/", views.creator_report, name="creator_report"),
    path("ops/disputes/", views.ops_list, name="list"),
    path("ops/disputes/<int:pk>/", views.ops_detail, name="detail"),
]
