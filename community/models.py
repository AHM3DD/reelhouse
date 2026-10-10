from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

from movies.models import Movie


class Comment(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="comments")
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name="comments")
    body = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["movie", "-created_at"], name="comment_movie_recent_idx"),
            models.Index(fields=["user", "-created_at"], name="comment_user_recent_idx"),
            models.Index(fields=["-created_at"], name="comment_recent_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=~Q(body=""), name="comment_body_not_empty"),
        ]

    def __str__(self):
        return f"{self.user} on {self.movie}: {self.body[:40]}"

    @property
    def is_edited(self):
        return (self.updated_at - self.created_at).total_seconds() > 2


class MovieRating(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ratings")
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name="ratings")
    score = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(10)])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "movie"], name="unique_rating_per_user_movie"),
            models.CheckConstraint(condition=Q(score__gte=1) & Q(score__lte=10), name="rating_score_1_to_10"),
        ]
        indexes = [models.Index(fields=["user", "-updated_at"], name="rating_user_recent_idx")]

    def __str__(self):
        return f"{self.user} rated {self.movie}: {self.score}/10"


class FavoriteMovie(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="favorites")
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name="favorited_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["user", "movie"], name="unique_favorite_per_user_movie")]
        indexes = [models.Index(fields=["user", "-created_at"], name="favorite_user_recent_idx")]

    def __str__(self):
        return f"{self.user} ♥ {self.movie}"


class WatchlistEntry(models.Model):
    """A user's personal movie list: films they want to watch or have watched."""

    class Status(models.TextChoices):
        WANT = "want", "Want to watch"
        WATCHED = "watched", "Watched"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="watchlist")
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name="watchlist_entries")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.WANT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        verbose_name_plural = "watchlist entries"
        constraints = [
            models.UniqueConstraint(fields=["user", "movie"], name="unique_list_entry_per_user_movie"),
            models.CheckConstraint(condition=Q(status__in=["want", "watched"]), name="list_status_valid"),
        ]
        indexes = [models.Index(fields=["user", "status", "-updated_at"], name="list_user_status_idx")]

    def __str__(self):
        return f"{self.user}: {self.movie} ({self.get_status_display()})"
