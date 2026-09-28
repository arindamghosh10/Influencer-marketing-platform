from django.urls import path

from . import views

app_name = "campaigns"
urlpatterns = [
    path("new/", views.create, name="create"),
    path("<int:pk>/", views.detail, name="detail"),
    path("<int:pk>/edit/", views.edit, name="edit"),
    path("<int:pk>/brief/edit/", views.edit_brief, name="edit_brief"),
    path("<int:pk>/brief/regenerate/", views.regenerate_brief, name="regenerate_brief"),
    path("<int:pk>/brief/confirm/", views.confirm_brief, name="confirm_brief"),
    path("<int:pk>/match/", views.rematch, name="rematch"),
    path("<int:pk>/candidates/<int:candidate_id>/toggle/", views.toggle_candidate, name="toggle_candidate"),
    path("<int:pk>/selection/confirm/", views.confirm_selection, name="confirm_selection"),
    path("<int:pk>/offers/send/", views.send_offers, name="send_offers"),
    path("<int:pk>/slots/<int:slot_id>/cancel/", views.cancel_slot, name="cancel_slot"),
]
