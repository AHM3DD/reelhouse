"""Business rules for community features, shared by the website views and the REST API."""
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Avg, Count, Q

from .models import Comment, FavoriteMovie, MovieRating, WatchlistEntry

COMMENTS_PER_PAGE = 10


# --- Reads ---------------------------------------------------------------------------


def community_stats(movie):
    if movie is None:
        return {"avg": None, "count": 0}
    stats = MovieRating.objects.filter(movie=movie).aggregate(avg=Avg("score"), count=Count("id"))
    return {"avg": round(stats["avg"], 1) if stats["avg"] is not None else None, "count": stats["count"]}


def movie_state(user, movie):
    """Everything the movie page needs about the community and the current user."""
    state = {"stats": community_stats(movie), "user_rating": None, "is_favorite": False, "list_status": ""}
    if movie is None or not user.is_authenticated:
        return state
    state["user_rating"] = (
        MovieRating.objects.filter(user=user, movie=movie).values_list("score", flat=True).first()
    )
    state["is_favorite"] = FavoriteMovie.objects.filter(user=user, movie=movie).exists()
    state["list_status"] = (
        WatchlistEntry.objects.filter(user=user, movie=movie).values_list("status", flat=True).first() or ""
    )
    return state


def favorite_ids_for(user, tmdb_ids):
    """TMDB ids (from the given ones) that the user has favorited: one query per page."""
    if not user.is_authenticated or not tmdb_ids:
        return set()
    return set(
        FavoriteMovie.objects.filter(user=user, movie__tmdb_id__in=set(tmdb_ids)).values_list(
            "movie__tmdb_id", flat=True
        )
    )


def comment_page(movie, page_number=1):
    queryset = (
        Comment.objects.filter(movie=movie).select_related("user__profile")
        if movie is not None
        else Comment.objects.none()
    )
    return Paginator(queryset, COMMENTS_PER_PAGE).get_page(page_number)


def collection_queryset(user, tab):
    if tab == "favorites":
        return FavoriteMovie.objects.filter(user=user).select_related("movie").order_by("-created_at", "-id")
    if tab == "ratings":
        return MovieRating.objects.filter(user=user).select_related("movie").order_by("-updated_at", "-id")
    if tab in (WatchlistEntry.Status.WANT, "watchlist"):
        return (
            WatchlistEntry.objects.filter(user=user, status=WatchlistEntry.Status.WANT)
            .select_related("movie")
            .order_by("-updated_at", "-id")
        )
    if tab == "watched":
        return (
            WatchlistEntry.objects.filter(user=user, status=WatchlistEntry.Status.WATCHED)
            .select_related("movie")
            .order_by("-updated_at", "-id")
        )
    if tab == "comments":
        return Comment.objects.filter(user=user).select_related("movie").order_by("-created_at", "-id")
    raise ValueError(f"Unknown collection tab: {tab}")


def profile_stats(user):
    ratings = MovieRating.objects.filter(user=user).aggregate(avg=Avg("score"), count=Count("id"))
    lists = WatchlistEntry.objects.filter(user=user).aggregate(
        want=Count("id", filter=Q(status=WatchlistEntry.Status.WANT)),
        watched=Count("id", filter=Q(status=WatchlistEntry.Status.WATCHED)),
    )
    return {
        "ratings": ratings["count"],
        "avg_rating": round(ratings["avg"], 1) if ratings["avg"] is not None else None,
        "favorites": FavoriteMovie.objects.filter(user=user).count(),
        "comments": Comment.objects.filter(user=user).count(),
        "watchlist": lists["want"],
        "watched": lists["watched"],
    }


# --- Writes --------------------------------------------------------------------------


def create_comment(user, movie, body):
    return Comment.objects.create(user=user, movie=movie, body=body)


def update_comment(comment, user, body):
    if comment.user_id != user.pk:
        raise PermissionError("Only the author can edit this comment.")
    comment.body = body
    comment.save(update_fields=["body", "updated_at"])
    return comment


def delete_comment(comment, user):
    if comment.user_id != user.pk:
        raise PermissionError("Only the author can delete this comment.")
    comment.delete()


def set_rating(user, movie, score):
    """Create or update the user's single rating for a movie."""
    if not isinstance(score, int) or not 1 <= score <= 10:
        raise ValidationError("Ratings must be whole numbers from 1 to 10.")
    try:
        with transaction.atomic():
            rating, _ = MovieRating.objects.update_or_create(user=user, movie=movie, defaults={"score": score})
    except IntegrityError:
        # A concurrent request created the row first; update it instead.
        MovieRating.objects.filter(user=user, movie=movie).update(score=score)
        rating = MovieRating.objects.get(user=user, movie=movie)
    return rating


def remove_rating(user, movie):
    deleted, _ = MovieRating.objects.filter(user=user, movie=movie).delete()
    return bool(deleted)


def add_favorite(user, movie):
    """Idempotent: returns (favorite, created)."""
    try:
        with transaction.atomic():
            return FavoriteMovie.objects.get_or_create(user=user, movie=movie)
    except IntegrityError:
        return FavoriteMovie.objects.get(user=user, movie=movie), False


def remove_favorite(user, movie):
    deleted, _ = FavoriteMovie.objects.filter(user=user, movie=movie).delete()
    return bool(deleted)


def set_list_status(user, movie, status):
    """status: 'want', 'watched' or 'none' (removes the entry)."""
    if status == "none":
        WatchlistEntry.objects.filter(user=user, movie=movie).delete()
        return None
    if status not in WatchlistEntry.Status.values:
        raise ValidationError("Unknown list status.")
    with transaction.atomic():
        entry, _ = WatchlistEntry.objects.update_or_create(user=user, movie=movie, defaults={"status": status})
    return entry
