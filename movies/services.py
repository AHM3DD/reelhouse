from datetime import timedelta

from django.http import Http404
from django.utils import timezone

from . import tmdb
from .models import Movie

SNAPSHOT_MAX_AGE = timedelta(days=3)


class MovieUnavailable(Exception):
    """The movie is unknown locally and TMDB cannot be reached to look it up."""


def snapshot_fields(detail):
    return {
        "title": detail.title[:255],
        "original_title": detail.original_title[:255],
        "overview": detail.overview,
        "poster_path": detail.poster_path,
        "backdrop_path": detail.backdrop_path,
        "release_date": detail.release_date,
        "runtime": detail.runtime,
        "vote_average": detail.vote_average or None,
        "genres": detail.genre_names,
        "synced_at": timezone.now(),
    }


def sync_movie(detail):
    movie, _ = Movie.objects.update_or_create(tmdb_id=detail.tmdb_id, defaults=snapshot_fields(detail))
    return movie


def refresh_snapshot_if_stale(detail):
    """Refresh an existing snapshot from freshly fetched details (never creates rows)."""
    if detail.stale:
        return
    Movie.objects.filter(tmdb_id=detail.tmdb_id, synced_at__lt=timezone.now() - SNAPSHOT_MAX_AGE).update(
        **snapshot_fields(detail)
    )


def ensure_movie(tmdb_id):
    """Return the local Movie row for a TMDB id, creating/refreshing it from TMDB as needed.

    Validates that the id really exists on TMDB before creating anything, so users cannot
    fill the table with junk ids. Raises Http404 for unknown ids and MovieUnavailable when
    TMDB is down and nothing is stored locally.
    """
    movie = Movie.objects.filter(tmdb_id=tmdb_id).first()
    if movie and movie.synced_at >= timezone.now() - SNAPSHOT_MAX_AGE:
        return movie
    try:
        detail = tmdb.movie_detail(tmdb_id)
    except tmdb.TMDBNotFound:
        if movie:
            return movie
        raise Http404("Movie not found.")
    except tmdb.TMDBError as exc:
        if movie:
            return movie
        raise MovieUnavailable from exc
    return sync_movie(detail)
