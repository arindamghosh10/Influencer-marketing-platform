from django.urls import path

from . import views

app_name = "contracts"
urlpatterns = [
    path("sign/", views.sign, name="sign"),
    path("sign/verify/", views.verify, name="verify"),
    path("sign/resend/", views.resend, name="resend"),
    path("consents/", views.consents, name="consents"),
    path("consents/<str:scope>/", views.toggle_consent, name="toggle_consent"),
    path("agreements/<int:pk>/", views.agreement_detail, name="agreement"),
]
