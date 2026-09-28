from django.urls import path

from . import views

app_name = "creators"
urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("onboarding/", views.onboarding, name="onboarding"),
    path("onboarding/<slug:step>/", views.onboarding, name="onboarding_step"),
    path("instagram/callback/", views.instagram_callback, name="ig_callback"),
    path("instagram/resync/", views.resync_instagram, name="resync"),
    path("submit/", views.submit_for_review, name="submit"),
]
