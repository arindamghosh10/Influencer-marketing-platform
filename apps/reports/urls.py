from django.urls import path

from . import views

app_name = "reports"
urlpatterns = [
    path("brand/library/", views.library, name="library"),
    path("brand/billing/", views.billing, name="billing"),
    path("brand/campaigns/<int:pk>/report/", views.campaign_report, name="campaign_report"),
    path("creator/earnings/", views.earnings, name="earnings"),
    path("creator/earnings/statement/<str:fy>/", views.statement, name="statement"),
]
