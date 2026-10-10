from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve

admin.site.site_header = "Reelhouse administration"
admin.site.site_title = "Reelhouse admin"
admin.site.index_title = "Community & catalogue"

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path("api/", include("api.urls")),
    path("", include("accounts.urls")),
    path("", include("community.urls")),
    path("", include("movies.urls")),
]

if settings.SERVE_MEDIA:
    # Avatars are re-encoded server-side before storage, so serving them directly is safe.
    # At scale, serve /media/ from a reverse proxy or object storage instead.
    media_prefix = settings.MEDIA_URL.strip("/")
    urlpatterns += [
        re_path(rf"^{media_prefix}/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
    ]
