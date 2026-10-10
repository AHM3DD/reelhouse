"""TMDB API client with caching, timeouts, cooldown on rate limits and stale fallbacks.

Every response is cached twice: a "fresh" copy with a short TTL and a "stale" copy kept
for a week. When TMDB is slow, rate-limiting us, or down, callers get the stale copy
(flagged with `stale=True`) instead of an error whenever one exists.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import date

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

MAX_PAGE = 500  # TMDB refuses pages beyond 500
STALE_TTL = 7 * 24 * 3600
COOLDOWN_KEY = "tmdb:cooldown"

TTL_LISTS = 30 * 60
TTL_TRENDING = 60 * 60
TTL_GENRES = 24 * 3600
TTL_DETAIL = 6 * 3600
TTL_SEARCH = 15 * 60

_http = requests.Session()
_http.headers.update({"Accept": "application/json", "User-Agent": "Reelhouse/1.0"})


class TMDBError(Exception):
    """Base class for TMDB failures."""


class TMDBUnavailable(TMDBError):
    """TMDB could not be reached (timeout, outage, rate limit, missing/invalid key)."""


class TMDBNotFound(TMDBError):
    """The requested resource does not exist on TMDB."""


# ---------------------------------------------------------------------------
# Normalised data structures used by views, templates and the API.
# ---------------------------------------------------------------------------


def _parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


@dataclass
class Genre:
    id: int
    name: str


@dataclass
class MovieSummary:
    tmdb_id: int
    title: str
    original_title: str = ""
    overview: str = ""
    poster_path: str = ""
    backdrop_path: str = ""
    release_date: date | None = None
    vote_average: float = 0.0
    vote_count: int = 0
    genre_ids: list[int] = field(default_factory=list)

    @property
    def year(self):
        return self.release_date.year if self.release_date else None

    @classmethod
    def from_api(cls, data):
        return cls(
            tmdb_id=int(data["id"]),
            title=data.get("title") or data.get("original_title") or "Untitled",
            original_title=data.get("original_title") or "",
            overview=data.get("overview") or "",
            poster_path=data.get("poster_path") or "",
            backdrop_path=data.get("backdrop_path") or "",
            release_date=_parse_date(data.get("release_date")),
            vote_average=float(data.get("vote_average") or 0),
            vote_count=int(data.get("vote_count") or 0),
            genre_ids=list(data.get("genre_ids") or []),
        )


@dataclass
class Person:
    tmdb_id: int
    name: str
    role: str = ""
    profile_path: str = ""


@dataclass
class MovieDetail(MovieSummary):
    tagline: str = ""
    runtime: int | None = None
    status: str = ""
    original_language: str = ""
    budget: int = 0
    revenue: int = 0
    homepage: str = ""
    imdb_id: str = ""
    genres: list[Genre] = field(default_factory=list)
    cast: list[Person] = field(default_factory=list)
    directors: list[Person] = field(default_factory=list)
    writers: list[Person] = field(default_factory=list)
    trailer_key: str = ""
    recommendations: list[MovieSummary] = field(default_factory=list)
    stale: bool = False

    @property
    def genre_names(self):
        return [genre.name for genre in self.genres]

    @classmethod
    def from_api(cls, data):
        base = MovieSummary.from_api(data)
        credits = data.get("credits") or {}
        crew = credits.get("crew") or []
        videos = (data.get("videos") or {}).get("results") or []
        trailer = next(
            (
                v
                for v in videos
                if v.get("site") == "YouTube" and v.get("type") == "Trailer" and v.get("key")
            ),
            None,
        )
        return cls(
            **base.__dict__,
            tagline=data.get("tagline") or "",
            runtime=data.get("runtime") or None,
            status=data.get("status") or "",
            original_language=(data.get("original_language") or "").upper(),
            budget=int(data.get("budget") or 0),
            revenue=int(data.get("revenue") or 0),
            homepage=data.get("homepage") or "",
            imdb_id=data.get("imdb_id") or "",
            genres=[Genre(id=g["id"], name=g["name"]) for g in data.get("genres") or [] if "id" in g],
            cast=[
                Person(tmdb_id=p["id"], name=p.get("name", ""), role=p.get("character") or "",
                       profile_path=p.get("profile_path") or "")
                for p in (credits.get("cast") or [])[:12]
            ],
            directors=[
                Person(tmdb_id=p["id"], name=p.get("name", ""), role="Director")
                for p in crew if p.get("job") == "Director"
            ],
            writers=_unique_people(
                Person(tmdb_id=p["id"], name=p.get("name", ""), role=p.get("job", ""))
                for p in crew if p.get("department") == "Writing"
            )[:3],
            trailer_key=trailer["key"] if trailer else "",
            recommendations=[
                MovieSummary.from_api(m) for m in ((data.get("recommendations") or {}).get("results") or [])[:12]
            ],
        )


def _unique_people(people):
    seen, result = set(), []
    for person in people:
        if person.tmdb_id not in seen:
            seen.add(person.tmdb_id)
            result.append(person)
    return result


@dataclass
class Page:
    results: list[MovieSummary]
    page: int = 1
    total_pages: int = 1
    total_results: int = 0
    stale: bool = False

    @classmethod
    def from_api(cls, data, stale=False):
        return cls(
            results=[MovieSummary.from_api(m) for m in data.get("results") or [] if m.get("id")],
            page=int(data.get("page") or 1),
            total_pages=min(int(data.get("total_pages") or 1), MAX_PAGE),
            total_results=int(data.get("total_results") or 0),
            stale=stale,
        )

    @property
    def has_previous(self):
        return self.page > 1

    @property
    def has_next(self):
        return self.page < self.total_pages

    @property
    def previous_page_number(self):
        return self.page - 1

    @property
    def next_page_number(self):
        return self.page + 1


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------


class TMDBClient:
    def __init__(self, api_key=None, base_url=None, timeout=None, language=None, region=None):
        config = settings.TMDB
        self.api_key = api_key if api_key is not None else config["API_KEY"]
        self.base_url = (base_url or config["BASE_URL"]).rstrip("/")
        self.timeout = timeout or config["TIMEOUT"]
        self.language = language or config["LANGUAGE"]
        self.region = region if region is not None else config["REGION"]

    @property
    def configured(self):
        return bool(self.api_key)

    def _cache_key(self, path, params):
        raw = json.dumps([path, sorted(params.items())], default=str)
        return "tmdb:" + hashlib.sha256(raw.encode()).hexdigest()

    def get(self, path, params=None, ttl=TTL_LISTS):
        """GET a TMDB endpoint. Returns (data, stale)."""
        params = {k: v for k, v in (params or {}).items() if v not in (None, "")}
        params.setdefault("language", self.language)
        key = self._cache_key(path, params)

        cached = cache.get(key)
        if cached is not None:
            return cached, False

        stale_key = key + ":stale"
        try:
            data = self._fetch(path, params)
        except TMDBUnavailable:
            stale = cache.get(stale_key)
            if stale is not None:
                return stale, True
            raise

        cache.set(key, data, ttl)
        cache.set(stale_key, data, STALE_TTL)
        return data, False

    def _fetch(self, path, params):
        if not self.configured:
            raise TMDBUnavailable("TMDB_API_KEY is not configured.")
        if cache.get(COOLDOWN_KEY):
            raise TMDBUnavailable("TMDB is cooling down after recent failures.")

        url = f"{self.base_url}{path}"
        try:
            # (connect, read) timeouts. The key is a query parameter, so never log `url` + params.
            response = _http.get(url, params={**params, "api_key": self.api_key}, timeout=(3.05, self.timeout))
        except requests.Timeout as exc:
            logger.warning("TMDB timeout on %s", path)
            self._cooldown(15)
            raise TMDBUnavailable("TMDB request timed out.") from exc
        except requests.RequestException as exc:
            logger.warning("TMDB request error on %s: %s", path, type(exc).__name__)
            self._cooldown(15)
            raise TMDBUnavailable("TMDB could not be reached.") from exc

        status = response.status_code
        if status == 404:
            raise TMDBNotFound(path)
        if status == 401:
            logger.error("TMDB rejected the API key (401). Check TMDB_API_KEY.")
            self._cooldown(60)
            raise TMDBUnavailable("TMDB rejected the API key.")
        if status == 429:
            retry_after = response.headers.get("Retry-After", "10")
            seconds = int(retry_after) if str(retry_after).isdigit() else 10
            logger.warning("TMDB rate limit hit on %s; cooling down %ss", path, seconds)
            self._cooldown(max(1, min(seconds, 60)))
            raise TMDBUnavailable("TMDB rate limit reached.")
        if status >= 500:
            logger.warning("TMDB server error %s on %s", status, path)
            self._cooldown(15)
            raise TMDBUnavailable(f"TMDB returned {status}.")
        if status >= 400:
            logger.warning("TMDB client error %s on %s", status, path)
            raise TMDBError(f"TMDB returned {status}.")

        try:
            return response.json()
        except ValueError as exc:
            logger.warning("TMDB returned invalid JSON on %s", path)
            raise TMDBUnavailable("TMDB returned an invalid response.") from exc

    @staticmethod
    def _cooldown(seconds):
        cache.set(COOLDOWN_KEY, True, seconds)


def get_client():
    return TMDBClient()


# ---------------------------------------------------------------------------
# High-level operations
# ---------------------------------------------------------------------------

CATEGORIES = {
    "trending": ("Trending this week", "/trending/movie/week", TTL_TRENDING),
    "popular": ("Popular", "/movie/popular", TTL_LISTS),
    "top-rated": ("Top rated", "/movie/top_rated", TTL_LISTS),
    "upcoming": ("Upcoming", "/movie/upcoming", TTL_LISTS),
    "now-playing": ("Now playing", "/movie/now_playing", TTL_LISTS),
}

SORT_OPTIONS = {
    "popularity.desc": "Most popular",
    "vote_average.desc": "Highest rated",
    "primary_release_date.desc": "Newest releases",
    "primary_release_date.asc": "Oldest releases",
    "revenue.desc": "Box office",
    "title.asc": "Title A-Z",
}


def clamp_page(page):
    try:
        page = int(page)
    except (TypeError, ValueError):
        return 1
    return max(1, min(page, MAX_PAGE))


def category(slug, page=1):
    _, path, ttl = CATEGORIES[slug]
    client = get_client()
    params = {"page": clamp_page(page)}
    if slug in ("upcoming", "now-playing"):
        params["region"] = client.region
    data, stale = client.get(path, params, ttl=ttl)
    return Page.from_api(data, stale=stale)


def genres():
    data, _ = get_client().get("/genre/movie/list", ttl=TTL_GENRES)
    return [Genre(id=g["id"], name=g["name"]) for g in data.get("genres") or []]


def discover(genre_id=None, sort="popularity.desc", year=None, page=1):
    params = {
        "page": clamp_page(page),
        "sort_by": sort if sort in SORT_OPTIONS else "popularity.desc",
        "include_adult": "false",
        "with_genres": genre_id,
        "primary_release_year": year,
    }
    if params["sort_by"].startswith("vote_average"):
        params["vote_count.gte"] = 300  # keep obscure 10/10 single-vote titles out
    data, stale = get_client().get("/discover/movie", params, ttl=TTL_LISTS)
    return Page.from_api(data, stale=stale)


def search(query, page=1):
    query = (query or "").strip()[:100]
    if not query:
        return Page(results=[])
    data, stale = get_client().get(
        "/search/movie", {"query": query, "page": clamp_page(page), "include_adult": "false"}, ttl=TTL_SEARCH
    )
    return Page.from_api(data, stale=stale)


def movie_detail(tmdb_id):
    data, stale = get_client().get(
        f"/movie/{int(tmdb_id)}", {"append_to_response": "credits,videos,recommendations"}, ttl=TTL_DETAIL
    )
    detail = MovieDetail.from_api(data)
    detail.stale = stale
    return detail
