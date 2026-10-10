"""HTMX-first endpoints for comments, ratings, favorites and the personal movie list.

Every endpoint also works without JavaScript (plain form POST + redirect), and every
write checks authentication and ownership on the server.
"""
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from core.htmx import is_htmx, login_required_htmx, render_partial, safe_next_url
from core.ratelimit import ratelimit
from movies.models import Movie
from movies.services import MovieUnavailable, ensure_movie

from . import services
from .forms import CommentForm, FavoriteForm, ListStatusForm, RatingForm
from .models import Comment

FAVORITE_VARIANTS = {"card", "detail", "hero"}


def _movie_url(tmdb_id, anchor=""):
    return reverse("movies:detail", kwargs={"tmdb_id": tmdb_id}) + anchor


def _back(request, tmdb_id, anchor=""):
    return redirect(safe_next_url(request) or _movie_url(tmdb_id, anchor))


def _resolve_movie(request, tmdb_id):
    """Return (movie, None) or (None, error_response) when TMDB is down and nothing is cached."""
    try:
        return ensure_movie(tmdb_id), None
    except MovieUnavailable:
        message = "Movie details are temporarily unavailable. Please try again in a moment."
        if is_htmx(request):
            return None, render(request, "partials/inline_error.html", {"message": message}, status=503)
        messages.error(request, message)
        return None, _back(request, tmdb_id)


def _own_comment(request, pk):
    comment = get_object_or_404(Comment.objects.select_related("user__profile", "movie"), pk=pk)
    if comment.user_id != request.user.pk:
        raise PermissionDenied("You can only change your own comments.")
    return comment


def _comments_context(tmdb_id, movie, form=None, page_number=1):
    page = services.comment_page(movie, page_number)
    return {
        "tmdb_id": tmdb_id,
        "movie": movie,
        "comments_page": page,
        "comment_count": page.paginator.count,
        "comment_form": form or CommentForm(),
    }


# --- Comments ------------------------------------------------------------------------


@require_GET
def comment_list(request, tmdb_id):
    """Next page of comments for the "Load more" button."""
    if not is_htmx(request):
        return redirect(_movie_url(tmdb_id, "#comments"))
    movie = Movie.objects.filter(tmdb_id=tmdb_id).first()
    page = services.comment_page(movie, request.GET.get("page"))
    return render_partial(request, "community/partials/comment_page.html", {"comments_page": page, "tmdb_id": tmdb_id})


@require_POST
@login_required_htmx
@ratelimit("comment", "6/m", key="user")
def comment_create(request, tmdb_id):
    movie, error = _resolve_movie(request, tmdb_id)
    if error:
        return error
    form = CommentForm(request.POST)
    if form.is_valid():
        services.create_comment(request.user, movie, form.cleaned_data["body"])
        messages.success(request, "Your comment was posted.")
        form = None
        if not is_htmx(request):
            return redirect(_movie_url(tmdb_id, "#comments"))
    elif not is_htmx(request):
        messages.error(request, " ".join(form.errors.get("body", ["Could not post your comment."])))
        return redirect(_movie_url(tmdb_id, "#comments"))
    return render_partial(request, "community/partials/comments_section.html", _comments_context(tmdb_id, movie, form))


@require_GET
def comment_detail(request, pk):
    comment = get_object_or_404(Comment.objects.select_related("user__profile", "movie"), pk=pk)
    if not is_htmx(request):
        return redirect(_movie_url(comment.movie.tmdb_id, f"#comment-{comment.pk}"))
    return render_partial(request, "community/partials/comment.html", {"comment": comment})


@require_http_methods(["GET", "POST"])
@login_required_htmx
def comment_edit(request, pk):
    comment = _own_comment(request, pk)
    if request.method == "POST":
        form = CommentForm(request.POST, instance=comment)
        if form.is_valid():
            services.update_comment(comment, request.user, form.cleaned_data["body"])
            messages.success(request, "Comment updated.")
            if is_htmx(request):
                return render_partial(request, "community/partials/comment.html", {"comment": comment})
            return redirect(_movie_url(comment.movie.tmdb_id, f"#comment-{comment.pk}"))
        comment.refresh_from_db(fields=["body"])  # keep the stored text intact for re-rendering
    else:
        form = CommentForm(instance=comment)
    context = {"comment": comment, "form": form}
    if is_htmx(request):
        return render_partial(request, "community/partials/comment_edit_form.html", context)
    return render(request, "community/comment_edit.html", context)


@require_POST
@login_required_htmx
def comment_delete(request, pk):
    comment = _own_comment(request, pk)
    tmdb_id = comment.movie.tmdb_id
    movie = comment.movie
    services.delete_comment(comment, request.user)
    messages.success(request, "Comment deleted.")
    if not is_htmx(request):
        return redirect(_movie_url(tmdb_id, "#comments"))
    remaining = Comment.objects.filter(movie=movie).count()
    return render_partial(request, "community/partials/comment_deleted.html", {"comment_count": remaining})


# --- Ratings -------------------------------------------------------------------------


def _rating_response(request, tmdb_id, movie, error=""):
    if not is_htmx(request):
        if error:
            messages.error(request, error)
        return _back(request, tmdb_id, "#your-rating")
    context = {"tmdb_id": tmdb_id, "rating_error": error, "as_partial": True, **services.movie_state(request.user, movie)}
    return render_partial(request, "community/partials/rating_widget.html", context)


@require_POST
@login_required_htmx
@ratelimit("rating", "30/m", key="user")
def rate(request, tmdb_id):
    form = RatingForm(request.POST)
    if not form.is_valid():
        movie = Movie.objects.filter(tmdb_id=tmdb_id).first()
        return _rating_response(request, tmdb_id, movie, error=form.errors["score"][0])
    movie, error = _resolve_movie(request, tmdb_id)
    if error:
        return error
    services.set_rating(request.user, movie, form.cleaned_data["score"])
    messages.success(request, f"You rated {movie.title} {form.cleaned_data['score']}/10.")
    return _rating_response(request, tmdb_id, movie)


@require_POST
@login_required_htmx
def rate_remove(request, tmdb_id):
    movie = get_object_or_404(Movie, tmdb_id=tmdb_id)
    if services.remove_rating(request.user, movie):
        messages.info(request, "Your rating was removed.")
    return _rating_response(request, tmdb_id, movie)


# --- Favorites -----------------------------------------------------------------------


@require_POST
@login_required_htmx
@ratelimit("favorite", "60/m", key="user")
def favorite(request, tmdb_id):
    form = FavoriteForm(request.POST)
    if not form.is_valid():
        return render(request, "partials/inline_error.html", {"message": "Invalid request."}, status=400)
    variant = request.POST.get("variant") if request.POST.get("variant") in FAVORITE_VARIANTS else "card"

    if form.cleaned_data["action"] == "add":
        movie, error = _resolve_movie(request, tmdb_id)
        if error:
            return error
        _, created = services.add_favorite(request.user, movie)
        if created:
            messages.success(request, f"Added {movie.title} to your favorites.")
        is_favorite = True
    else:
        movie = Movie.objects.filter(tmdb_id=tmdb_id).first()
        if movie and services.remove_favorite(request.user, movie):
            messages.info(request, f"Removed {movie.title} from your favorites.")
        is_favorite = False

    if not is_htmx(request):
        return _back(request, tmdb_id)
    return render_partial(
        request,
        "community/partials/favorite_button.html",
        {"tmdb_id": tmdb_id, "is_favorite": is_favorite, "variant": variant, "title": movie.title if movie else ""},
    )


# --- Personal movie list -------------------------------------------------------------


@require_POST
@login_required_htmx
@ratelimit("list", "60/m", key="user")
def list_status(request, tmdb_id):
    form = ListStatusForm(request.POST)
    if not form.is_valid():
        return render(request, "partials/inline_error.html", {"message": "Invalid request."}, status=400)
    status = form.cleaned_data["status"]
    if status == "none":
        movie = get_object_or_404(Movie, tmdb_id=tmdb_id)
    else:
        movie, error = _resolve_movie(request, tmdb_id)
        if error:
            return error
    services.set_list_status(request.user, movie, status)
    messages.success(
        request,
        {
            "want": f"Added {movie.title} to your watchlist.",
            "watched": f"Marked {movie.title} as watched.",
            "none": f"Removed {movie.title} from your list.",
        }[status],
    )
    if not is_htmx(request):
        return _back(request, tmdb_id)
    return render_partial(
        request,
        "community/partials/list_controls.html",
        {"tmdb_id": tmdb_id, "list_status": "" if status == "none" else status, "compact": request.POST.get("compact") == "1"},
    )
