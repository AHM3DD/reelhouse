from django.core.cache import cache
from django.test import RequestFactory, TestCase

from core.ratelimit import is_rate_limited, parse_rate


class CoreTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_health_check(self):
        response = self.client.get("/healthz/", HTTP_HOST="unlisted-host.internal")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["database"], True)

    def test_custom_404_page(self):
        response = self.client.get("/definitely/not/here/")
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "This scene was cut", status_code=404)

    def test_parse_rate(self):
        self.assertEqual(parse_rate("10/5m"), (10, 300))
        self.assertEqual(parse_rate("3/h"), (3, 3600))

    def test_rate_limit_counts_per_client(self):
        factory = RequestFactory()
        request = factory.post("/", REMOTE_ADDR="10.0.0.1")
        request.user = type("Anon", (), {"is_authenticated": False})()
        results = [is_rate_limited(request, "test", "2/m") for _ in range(3)]
        self.assertEqual(results, [False, False, True])
        other = factory.post("/", REMOTE_ADDR="10.0.0.2")
        other.user = request.user
        self.assertFalse(is_rate_limited(other, "test", "2/m"))

    def test_security_headers(self):
        response = self.client.get("/accounts/login/")
        self.assertEqual(response["X-Frame-Options"], "DENY")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
