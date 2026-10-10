import mimetypes

from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        # Avatars are stored as WebP; older mimetypes tables don't know the extension,
        # which would make uploads be served as application/octet-stream.
        mimetypes.add_type("image/webp", ".webp")
