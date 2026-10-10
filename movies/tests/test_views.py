from datetime import timedelta

import requests
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from community.models import FavoriteMovie
from movies.models import Movie
from movies.services import ensure_movie
from movies.testing import GENRES, TMDBTestCase, detail_payload, list_payload, make_movie, movie_payload

HX = {"HTTP_HX_REQUEST": "true", "HTTP_HX_TARGET": "results"}


class HomeViewTests(TMDBTestCase):
    def test_home_renders_movie_rows(self):
        self.route_home()
        response = self.client.get(reverse("movies:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Inception")
        self.assertContains(response, "Trending this week")
        self.assertContains(response, "Science Fiction")  # genre chips
        self.assertContains(response, "image.tmdb.org/t/p/w342/poster27205.jpg")
        self.assertNotContains(response, "test-api-key")

    def test_home_survives_tmdb_outage(self):
        for path in ("/trending/movie/week", "/movie/popular", "/movie/top_rated", "/movie/upcoming",
                     "/movie/now_playing", "/genre/movie/list"):
            self.route(path, requests.ConnectionError("down"))
        response = self.client.get(reverse("movies:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "reach our movie data provider")
        self.assertContains(response, "Latest discussions")

    def test_home_marks_favorites_for_logged_in_user(self):
        self.route_home()
        user = User.objects.create_user("ann", "ann@example.com", "pw-Secret-123")
        FavoriteMovie.objects.create(user=user, movie=make_movie())
        self.client.force_login(user)
        response = self.client.get(reverse("movies:home"))
        self.assertContains(response, 'aria-label="Remove Inception from favorites"')


class SearchAndBrowseTests(TMDBTestCase):
    def test_search_results(self):
        self.route("/search/movie", list_payload([movie_payload(438631, "Dune")], total_results=1))
        response = self.client.get(reverse("movies:search"), {"q": "dune"})
        self.assertContains(response, "Dune")
        self.assertEqual(self.http.call_args.kwargs["params"]["query"], "dune")

    def test_search_without_results_shows_empty_state(self):
        self.route("/search/movie", list_payload([]))
        response = self.client.get(reverse("movies:search"), {"q": "zzzzqqq"})
        self.assertContains(response, "No movies found for")

    def test_search_htmx_returns_partial(self):
        self.route("/search/movie", list_payload([movie_payload(438631, "Dune")]))
        response = self.client.get(reverse("movies:search"), {"q": "dune"}, **HX)
        self.assertContains(response, "Dune")
        self.assertNotContains(response, "<html")

    def test_search_when_tmdb_down(self):
        self.route("/search/movie", requests.Timeout("slow"))
        response = self.client.get(reverse("movies:search"), {"q": "dune"})
        self.assertContains(response, "Movies are unavailable right now")

    def test_browse_filters_by_genre_and_sort(self):
        self.route("/genre/movie/list", GENRES)
        self.route("/discover/movie", list_payload([movie_payload(1, "Space Film")]))
        response = self.client.get(reverse("movies:browse"), {"genre": "878", "sort": "vote_average.desc", "year": "2014"})
        self.assertContains(response, "Space Film")
        params = self.http.call_args.kwargs["params"]
        self.assertEqual(params["with_genres"], 878)
        self.assertEqual(params["sort_by"], "vote_average.desc")
        self.assertEqual(params["primary_release_year"], 2014)
        self.assertEqual(params["vote_count.gte"], 300)

    def test_browse_ignores_invalid_filters(self):
        self.route("/genre/movie/list", GENRES)
        self.route("/discover/movie", list_payload([]))
        response = self.client.get(reverse("movies:browse"), {"genre": "99999", "sort": "drop table", "year": "abc"}, **HX)
        self.assertEqual(response.status_code, 200)
        params = self.http.call_args.kwargs["params"]
        self.assertNotIn("with_genres", params)
        self.assertEqual(params["sort_by"], "popularity.desc")
        self.assertContains(response, "No movies match these filters")

    def test_category_pages(self):
        self.route("/movie/top_rated", list_payload([movie_payload(1, "Classic")], total_pages=3))
        response = self.client.get(reverse("movies:category", args=["top-rated"]), {"page": 2})
        self.assertContains(response, "Classic")
        self.assertContains(response, "Page <span")
        self.assertEqual(self.client.get(reverse("movies:category", args=["nope"])).status_code, 404)


class DetailViewTests(TMDBTestCase):
    def test_detail_page(self):
        self.route("/movie/27205", detail_payload())
        response = self.client.get(reverse("movies:detail", args=[27205]))
        self.assertContains(response, "Inception")
        self.assertContains(response, "Leonardo DiCaprio")
        self.assertContains(response, "2h 28m")
        self.assertContains(response, "No ratings yet")
        self.assertContains(response, "Log in to rate")
        self.assertFalse(Movie.objects.exists(), "viewing a page must not persist TMDB data")

    def test_detail_404(self):
        response = self.client.get(reverse("movies:detail", args=[123456789]))
        self.assertEqual(response.status_code, 404)

    def test_detail_degrades_to_snapshot(self):
        make_movie(title="Inception (saved)")
        self.route("/movie/27205", None, status=503)
        response = self.client.get(reverse("movies:detail", args=[27205]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Inception (saved)")
        self.assertContains(response, "Showing saved details")

    def test_detail_unavailable_without_snapshot(self):
        self.route("/movie/27205", None, status=503)
        response = self.client.get(reverse("movies:detail", args=[27205]))
        self.assertEqual(response.status_code, 503)
        self.assertContains(response, "temporarily unavailable", status_code=503)


class EnsureMovieTests(TMDBTestCase):
    def test_creates_snapshot_from_tmdb(self):
        self.route("/movie/27205", detail_payload())
        movie = ensure_movie(27205)
        self.assertEqual(movie.title, "Inception")
        self.assertEqual(movie.runtime, 148)
        self.assertEqual(movie.genres, ["Action", "Science Fiction"])

    def test_fresh_snapshot_skips_tmdb(self):
        make_movie()
        ensure_movie(27205)
        self.http.assert_not_called()

    def test_stale_snapshot_is_refreshed(self):
        make_movie(title="Old title", synced_at=timezone.now() - timedelta(days=10))
        self.route("/movie/27205", detail_payload())
        self.assertEqual(ensure_movie(27205).title, "Inception")
