from django.urls import path

from . import views

app_name = "core"
urlpatterns = [
    path("", views.landing, name="landing"),
    path("home/", views.home, name="home"),
    path("notifications/", views.notifications, name="notifications"),
    path("ops/", views.ops_dashboard, name="ops"),
    path("ops/run-jobs/", views.run_jobs, name="run_jobs"),
]
