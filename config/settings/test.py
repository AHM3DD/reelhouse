import tempfile

from .base import *  # noqa: F401,F403
from .base import MIDDLEWARE, SIMPLE_JWT, TMDB

DEBUG = False
SECRET_KEY = "test-secret-key-not-used-anywhere-else-0123456789"
SIMPLE_JWT["SIGNING_KEY"] = SECRET_KEY
ALLOWED_HOSTS = ["testserver", "localhost"]

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

# Tests never talk to the real TMDB: every HTTP call is mocked.
TMDB = {**TMDB, "API_KEY": "test-api-key", "REGION": "", "LANGUAGE": "en-US"}

MEDIA_ROOT = tempfile.mkdtemp(prefix="reelhouse-test-media-")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"null": {"class": "logging.NullHandler"}},
    "root": {"handlers": ["null"], "level": "CRITICAL"},
}

# WhiteNoise serves collected files in production; here static files come from the source tree.
MIDDLEWARE = [m for m in MIDDLEWARE if not m.startswith("whitenoise.")]
