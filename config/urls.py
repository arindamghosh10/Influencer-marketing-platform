from django.conf import settings
from django.conf.urls.static import static
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
    path("contracts/", include("apps.contracts.urls")),
    path("", include("apps.core.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
