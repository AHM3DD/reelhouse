from .base import *  # noqa: F401,F403
from .base import MIDDLEWARE, ALLOWED_HOSTS, SECRET_KEY, SIMPLE_JWT, env_bool

DEBUG = env_bool("DJANGO_DEBUG", True)

if not SECRET_KEY:
    SECRET_KEY = "django-insecure-development-only-key-do-not-use-in-production"
    SIMPLE_JWT["SIGNING_KEY"] = SECRET_KEY

ALLOWED_HOSTS = [*ALLOWED_HOSTS, "localhost", "127.0.0.1", "0.0.0.0"]

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
SERVE_MEDIA = True

REST_FRAMEWORK = {
    **REST_FRAMEWORK,  # noqa: F405
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
}

# WhiteNoise serves collected files in production; here static files come from the source tree.
MIDDLEWARE = [m for m in MIDDLEWARE if not m.startswith("whitenoise.")]
