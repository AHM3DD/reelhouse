import datetime

from django.http import Http404
from django.shortcuts import render

from community.forms import CommentForm
from community.models import Comment
from community.services import comment_page, favorite_ids_for, movie_state
from core.htmx import htmx_target, render_partial

from . import tmdb
from .models import Movie
from .services import refresh_snapshot_if_stale

HOME_ROWS = ["trending", "now-playing", "popular", "top-rated", "upcoming"]


def _ids(movies):
    return [m.tmdb_id for m in movies]


def home(request):
    rows, stale, failed = [], False, False
    for slug in HOME_ROWS:
        try:
            page = tmdb.category(slug)
        except tmdb.TMDBError:
            failed = True
            continue
        stale = stale or page.stale
        if page.results:
            rows.append({"slug": slug, "title": tmdb.CATEGORIES[slug][0], "movies": page.results[:18]})

    try:
        genre_list = tmdb.genres()
    except tmdb.TMDBError:
        genre_list = []

    hero, hero_genres = None, []
    if rows:
        candidates = [m for m in rows[0]["movies"][:6] if m.backdrop_path] or rows[0]["movies"][:1]
        if candidates:
            # Rotate the featured film daily among the top trending titles.
            hero = candidates[datetime.date.today().toordinal() % len(candidates)]
            genre_map = {g.id: g.name for g in genre_list}
            hero_genres = [genre_map[g] for g in hero.genre_ids if g in genre_map][:3]

    all_ids = [tmdb_id for row in rows for tmdb_id in _ids(row["movies"])]
    latest_comments = Comment.objects.select_related("user__profile", "movie").order_by("-created_at")[:6]

    return render(
        request,
        "movies/home.html",
        {
            "hero": hero,
            "hero_genres": hero_genres,
            "rows": rows,
            "genres": genre_list,
            "stale": stale,
            "failed": failed and not rows,
            "partial_failure": failed and bool(rows),
            "favorite_ids": favorite_ids_for(request.user, all_ids),
            "latest_comments": latest_comments,
        },
    )


def _results_response(request, template, context, partial="movies/partials/results.html"):
    page = context.get("page")
    context["favorite_ids"] = favorite_ids_for(request.user, _ids(page.results) if page else [])
    if htmx_target(request) == "results":
        return render_partial(request, partial, context)
    return render(request, template, context)


def category(request, slug):
    if slug not in tmdb.CATEGORIES:
        raise Http404("Unknown category.")
    page, error = None, False
    try:
        page = tmdb.category(slug, tmdb.clamp_page(request.GET.get("page")))
    except tmdb.TMDBError:
        error = True
    return _results_response(
        request,
        "movies/category.html",
        {
            "slug": slug,
            "title": tmdb.CATEGORIES[slug][0],
            "categories": [(key, value[0]) for key, value in tmdb.CATEGORIES.items()],
            "page": page,
            "error": error,
        },
    )


def _int_param(value, low, high):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return None
    return value if low <= value <= high else None


def browse(request):
    try:
        genre_list = tmdb.genres()
    except tmdb.TMDBError:
        genre_list = []

    genre_id = _int_param(request.GET.get("genre"), 1, 10**7)
    if genre_list and genre_id not in {g.id for g in genre_list}:
        genre_id = None
    sort = request.GET.get("sort", "popularity.desc")
    if sort not in tmdb.SORT_OPTIONS:
        sort = "popularity.desc"
    year = _int_param(request.GET.get("year"), 1900, datetime.date.today().year + 5)

    page, error = None, False
    try:
        page = tmdb.discover(genre_id=genre_id, sort=sort, year=year, page=tmdb.clamp_page(request.GET.get("page")))
    except tmdb.TMDBError:
        error = True

    selected_genre = next((g for g in genre_list if g.id == genre_id), None)
    return _results_response(
        request,
        "movies/browse.html",
        {
            "genres": genre_list,
            "genre_id": genre_id,
            "selected_genre": selected_genre,
            "sort": sort,
            "sort_options": tmdb.SORT_OPTIONS.items(),
            "year": year or "",
            "page": page,
            "error": error,
            "empty_message": "No movies match these filters. Try another genre or year.",
        },
        partial="movies/partials/browse_results.html",
    )


def search(request):
    query = request.GET.get("q", "").strip()[:100]
    page, error, suggestions, genre_list = None, False, [], []
    if query:
        try:
            page = tmdb.search(query, tmdb.clamp_page(request.GET.get("page")))
        except tmdb.TMDBError:
            error = True
    elif not htmx_target(request):
        try:
            suggestions = tmdb.category("trending").results[:12]
            genre_list = tmdb.genres()
        except tmdb.TMDBError:
            pass

    context = {
        "query": query,
        "page": page,
        "error": error,
        "suggestions": suggestions,
        "genres": genre_list,
        "empty_message": f"No movies found for “{query}”. Check the spelling or try another title.",
    }
    context["favorite_ids"] = favorite_ids_for(
        request.user, _ids(page.results) if page else _ids(suggestions)
    )
    if htmx_target(request) == "results":
        return render_partial(request, "movies/partials/search_results.html", context)
    return render(request, "movies/search.html", context)


def detail(request, tmdb_id):
    movie = Movie.objects.filter(tmdb_id=tmdb_id).first()
    degraded = False
    try:
        info = tmdb.movie_detail(tmdb_id)
        refresh_snapshot_if_stale(info)
    except tmdb.TMDBNotFound:
        raise Http404("Movie not found.")
    except tmdb.TMDBError:
        if movie is None:
            return render(request, "movies/unavailable.html", {"tmdb_id": tmdb_id}, status=503)
        info, degraded = movie, True

    comments = comment_page(movie, 1)
    recommendations = getattr(info, "recommendations", None) or []
    context = {
        "info": info,
        "tmdb_id": tmdb_id,
        "movie": movie,
        "degraded": degraded,
        "comments_page": comments,
        "comment_count": comments.paginator.count,
        "comment_form": CommentForm(),
        "recommendations": recommendations,
        "favorite_ids": favorite_ids_for(request.user, _ids(recommendations)),
        **movie_state(request.user, movie),
    }
    return render(request, "movies/detail.html", context)
