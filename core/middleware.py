import logging

from django.db import connection
from django.http import JsonResponse

logger = logging.getLogger(__name__)


class HealthCheckMiddleware:
    """Answer /healthz/ before host validation or HTTPS redirects run.

    Container health checks hit 127.0.0.1 over plain HTTP, which would otherwise be
    rejected by ALLOWED_HOSTS or redirected by SECURE_SSL_REDIRECT in production.
    """

    path = "/healthz/"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path != self.path:
            return self.get_response(request)
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            database_ok = True
        except Exception as exc:  # noqa: BLE001 - any failure means unhealthy
            logger.warning("Health check database probe failed: %s", type(exc).__name__)
            database_ok = False
        return JsonResponse(
            {"status": "ok" if database_ok else "unavailable", "database": database_ok},
            status=200 if database_ok else 503,
        )
