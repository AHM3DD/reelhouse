"""Test helpers: fake TMDB payloads and an HTTP mock. Never used at runtime."""
from datetime import date
from unittest import mock

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from .models import Movie


def movie_payload(tmdb_id, title, **extra):
    data = {
        "id": tmdb_id,
        "title": title,
        "original_title": title,
        "overview": f"Overview of {title}.",
        "poster_path": f"/poster{tmdb_id}.jpg",
        "backdrop_path": f"/backdrop{tmdb_id}.jpg",
        "release_date": "2010-07-16",
        "vote_average": 8.4,
        "vote_count": 35000,
        "genre_ids": [28, 878],
    }
    data.update(extra)
    return data


def list_payload(movies, page=1, total_pages=1, total_results=None):
    return {
        "page": page,
        "results": movies,
        "total_pages": total_pages,
        "total_results": len(movies) if total_results is None else total_results,
    }


def detail_payload(tmdb_id=27205, title="Inception", **extra):
    data = movie_payload(tmdb_id, title)
    data.pop("genre_ids")
    data.update(
        {
            "tagline": "Your mind is the scene of the crime.",
            "runtime": 148,
            "status": "Released",
            "original_language": "en",
            "budget": 160000000,
            "revenue": 839030630,
            "imdb_id": "tt1375666",
            "genres": [{"id": 28, "name": "Action"}, {"id": 878, "name": "Science Fiction"}],
            "credits": {
                "cast": [{"id": 6193, "name": "Leonardo DiCaprio", "character": "Cobb", "profile_path": "/leo.jpg"}],
                "crew": [
                    {"id": 525, "name": "Christopher Nolan", "job": "Director", "department": "Directing"},
                    {"id": 525, "name": "Christopher Nolan", "job": "Writer", "department": "Writing"},
                ],
            },
            "videos": {"results": [{"site": "YouTube", "type": "Trailer", "key": "YoHD9XEInc0"}]},
            "recommendations": {"results": [movie_payload(155, "The Dark Knight")]},
        }
    )
    data.update(extra)
    return data


GENRES = {"genres": [{"id": 28, "name": "Action"}, {"id": 878, "name": "Science Fiction"}, {"id": 18, "name": "Drama"}]}


class FakeResponse:
    def __init__(self, status_code=200, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class TMDBMockMixin:
    """Patches the TMDB HTTP session. Register responses with self.route(path, payload)."""

    def setUp(self):
        super().setUp()
        cache.clear()
        self.routes = {}
        patcher = mock.patch("movies.tmdb._http.get", side_effect=self._fake_get)
        self.http = patcher.start()
        self.addCleanup(patcher.stop)

    def route(self, path, payload=None, status=200, headers=None):
        self.routes[path] = FakeResponse(status, payload, headers)

    def _fake_get(self, url, params=None, timeout=None):
        path = url.split("/3", 1)[1]
        response = self.routes.get(path)
        if response is None:
            return FakeResponse(404, {"status_message": "not found"})
        if isinstance(response._payload, BaseException) and not isinstance(response._payload, ValueError):
            raise response._payload
        return response

    def route_home(self):
        movies = [movie_payload(27205, "Inception"), movie_payload(155, "The Dark Knight")]
        for path in ("/trending/movie/week", "/movie/popular", "/movie/top_rated", "/movie/upcoming", "/movie/now_playing"):
            self.route(path, list_payload(movies))
        self.route("/genre/movie/list", GENRES)


class TMDBTestCase(TMDBMockMixin, TestCase):
    pass


def make_movie(tmdb_id=27205, title="Inception", **extra):
    defaults = {
        "title": title,
        "poster_path": f"/poster{tmdb_id}.jpg",
        "release_date": date(2010, 7, 16),
        "vote_average": 8.4,
        "genres": ["Action"],
        "synced_at": timezone.now(),
    }
    defaults.update(extra)
    return Movie.objects.create(tmdb_id=tmdb_id, **defaults)
