from django.urls import path

from . import views

app_name = "payments"
urlpatterns = [
    path("campaigns/<int:campaign_id>/pay/", views.start, name="start"),
    path("orders/<int:pk>/checkout/", views.checkout, name="checkout"),
    path("orders/<int:pk>/confirm/", views.confirm, name="confirm"),
    path("orders/<int:pk>/invoice/", views.invoice, name="invoice"),
    path("refunds/<int:pk>/credit-note/", views.credit_note, name="credit_note"),
    path("webhooks/razorpay/", views.razorpay_webhook, name="razorpay_webhook"),
]
