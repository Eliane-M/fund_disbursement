from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("accounts.urls")),
    path("api/core/", include("apps.core.urls")),
    path("api/assessment/", include("apps.maturity_assessment.urls")),
    path("api/platform/", include("apps.platform.urls")),
]
