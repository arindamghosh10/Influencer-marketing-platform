from django.urls import path

from . import views

app_name = "brands"
urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("profile/", views.profile, name="profile"),
    path("profile/verify-domain/", views.verify_domain, name="verify_domain"),
    path("agreement/", views.agreement, name="agreement"),
    path("submit/", views.submit_for_review, name="submit"),
]
