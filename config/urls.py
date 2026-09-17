from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from django.urls import path, include

from apps.common.exceptions import handler404 as json_404
from apps.common.exceptions import handler500 as json_500

handler404 = json_404
handler500 = json_500

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("apps.urls")),
    path("api/docs/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
