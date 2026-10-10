import requests
from django.core.cache import cache
from django.test import override_settings

from movies import tmdb
from movies.testing import TMDBTestCase, detail_payload, list_payload, movie_payload


class TMDBClientTests(TMDBTestCase):
    def test_list_is_parsed_and_cached(self):
        self.route("/movie/popular", list_payload([movie_payload(1, "Alpha")], total_pages=900))
        page = tmdb.category("popular")
        self.assertEqual(page.results[0].title, "Alpha")
        self.assertEqual(page.results[0].year, 2010)
        self.assertEqual(page.total_pages, tmdb.MAX_PAGE)  # TMDB caps pages at 500
        tmdb.category("popular")
        self.assertEqual(self.http.call_count, 1, "second call must be served from cache")

    def test_api_key_is_sent_as_query_parameter_with_timeout(self):
        self.route("/movie/popular", list_payload([]))
        tmdb.category("popular")
        _, kwargs = self.http.call_args
        self.assertEqual(kwargs["params"]["api_key"], "test-api-key")
        self.assertIsNotNone(kwargs["timeout"])

    def test_timeout_raises_unavailable(self):
        self.route("/movie/popular", requests.Timeout("slow"))
        with self.assertRaises(tmdb.TMDBUnavailable):
            tmdb.category("popular")

    def test_connection_error_raises_unavailable(self):
        self.route("/movie/popular", requests.ConnectionError("down"))
        with self.assertRaises(tmdb.TMDBUnavailable):
            tmdb.category("popular")

    def test_stale_copy_is_served_when_tmdb_fails(self):
        self.route("/movie/popular", list_payload([movie_payload(1, "Alpha")]))
        tmdb.category("popular")
        # Expire the fresh copy, then make TMDB fail.
        client = tmdb.TMDBClient()
        cache.delete(client._cache_key("/movie/popular", {"page": 1, "language": "en-US"}))
        self.route("/movie/popular", None, status=503)
        page = tmdb.category("popular")
        self.assertTrue(page.stale)
        self.assertEqual(page.results[0].title, "Alpha")

    def test_rate_limit_triggers_cooldown(self):
        self.route("/movie/popular", None, status=429, headers={"Retry-After": "5"})
        with self.assertRaises(tmdb.TMDBUnavailable):
            tmdb.category("popular")
        self.assertTrue(cache.get(tmdb.COOLDOWN_KEY))
        with self.assertRaises(tmdb.TMDBUnavailable):
            tmdb.category("top-rated")
        self.assertEqual(self.http.call_count, 1, "no requests while cooling down")

    def test_server_error_raises_unavailable(self):
        self.route("/movie/popular", None, status=500)
        with self.assertRaises(tmdb.TMDBUnavailable):
            tmdb.category("popular")

    def test_invalid_json_raises_unavailable(self):
        self.route("/movie/popular", ValueError("bad json"))
        with self.assertRaises(tmdb.TMDBUnavailable):
            tmdb.category("popular")

    def test_not_found(self):
        with self.assertRaises(tmdb.TMDBNotFound):
            tmdb.movie_detail(424242)

    @override_settings(TMDB={**tmdb.settings.TMDB, "API_KEY": ""})
    def test_missing_api_key_never_calls_tmdb(self):
        with self.assertRaises(tmdb.TMDBUnavailable):
            tmdb.category("popular")
        self.http.assert_not_called()

    def test_empty_search_does_not_call_tmdb(self):
        page = tmdb.search("   ")
        self.assertEqual(page.results, [])
        self.http.assert_not_called()

    def test_detail_parsing(self):
        self.route("/movie/27205", detail_payload())
        detail = tmdb.movie_detail(27205)
        self.assertEqual(detail.runtime, 148)
        self.assertEqual(detail.genre_names, ["Action", "Science Fiction"])
        self.assertEqual([p.name for p in detail.directors], ["Christopher Nolan"])
        self.assertEqual(len(detail.writers), 1, "duplicate crew entries are collapsed")
        self.assertEqual(detail.trailer_key, "YoHD9XEInc0")
        self.assertEqual(detail.recommendations[0].title, "The Dark Knight")

    def test_missing_fields_are_tolerated(self):
        self.route("/movie/popular", list_payload([{"id": 9, "title": "Bare", "release_date": ""}]))
        movie = tmdb.category("popular").results[0]
        self.assertIsNone(movie.release_date)
        self.assertEqual(movie.poster_path, "")

    def test_clamp_page(self):
        self.assertEqual(tmdb.clamp_page("9999"), 500)
        self.assertEqual(tmdb.clamp_page("abc"), 1)
        self.assertEqual(tmdb.clamp_page(-3), 1)
