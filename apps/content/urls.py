from django.urls import path

from . import views

app_name = "content"
urlpatterns = [
    path("creator/campaigns/<int:slot_id>/", views.workspace, name="workspace"),
    path("creator/campaigns/<int:slot_id>/draft/", views.submit_draft, name="submit_draft"),
    path("creator/campaigns/<int:slot_id>/approve/", views.final_approve, name="final_approve"),
    path("creator/campaigns/<int:slot_id>/posted/", views.self_post, name="self_post"),
    path("brand/campaigns/<int:campaign_id>/creators/<int:slot_id>/", views.review, name="review"),
    path(
        "brand/campaigns/<int:campaign_id>/creators/<int:slot_id>/review/",
        views.review_action,
        name="review_action",
    ),
    path("content/files/<int:asset_id>/", views.asset_file, name="asset_file"),
    path("content/public/<str:token>/", views.public_asset, name="public_asset"),
]
