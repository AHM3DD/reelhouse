import logging

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import ALLOWED_HOSTS, SECRET_KEY, STORAGES, TMDB, env_bool, env_int

DEBUG = False

if not SECRET_KEY or SECRET_KEY.startswith("change-me") or len(SECRET_KEY) < 40:
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY must be set to a random value of at least 40 characters in production."
    )
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must list the host names that serve this site.")
if not TMDB["API_KEY"]:
    logging.getLogger(__name__).warning("TMDB_API_KEY is not set; movie data will be unavailable.")

STORAGES = {
    **STORAGES,
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# HTTPS hardening. Disable the first two only when testing locally over plain HTTP.
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
SESSION_COOKIE_SECURE = env_bool("DJANGO_SECURE_COOKIES", True)
CSRF_COOKIE_SECURE = env_bool("DJANGO_SECURE_COOKIES", True)
SECURE_HSTS_SECONDS = env_int("DJANGO_SECURE_HSTS_SECONDS", 2592000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", False)
SECURE_HSTS_PRELOAD = env_bool("DJANGO_SECURE_HSTS_PRELOAD", False)
if env_bool("DJANGO_BEHIND_PROXY", False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SERVE_MEDIA = env_bool("DJANGO_SERVE_MEDIA", True)
