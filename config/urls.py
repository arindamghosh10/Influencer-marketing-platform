from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("brand/", include("apps.brands.urls")),
    path("creator/", include("apps.creators.urls")),
    path("brand/campaigns/", include("apps.campaigns.urls")),
    path("creator/offers/", include("apps.offers.urls")),
    path("payments/", include("apps.payments.urls")),
    path("", include("apps.content.urls")),
    path("contracts/", include("apps.contracts.urls")),
    path("", include("apps.core.urls")),
]
# Uploaded files (KYC documents, drafts) are never served directly from MEDIA_ROOT; they go
# through permission-checked views such as content:asset_file.
