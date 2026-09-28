from django.urls import path

from . import views

app_name = "offers"
urlpatterns = [
    path("<int:pk>/", views.detail, name="detail"),
    path("<int:pk>/accept/", views.accept, name="accept"),
    path("<int:pk>/accepted/", views.complete, name="complete"),
    path("<int:pk>/decline/", views.decline, name="decline"),
]
