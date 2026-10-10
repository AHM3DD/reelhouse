from django.db import models
from django.urls import reverse


class Movie(models.Model):
    """Local snapshot of a TMDB movie.

    Rows are created only when a user interacts with a movie (comment, rating, favorite,
    watchlist), so profiles and collections render without calling TMDB. The full
    catalogue is never mirrored.
    """

    tmdb_id = models.PositiveIntegerField(unique=True)
    title = models.CharField(max_length=255)
    original_title = models.CharField(max_length=255, blank=True)
    overview = models.TextField(blank=True)
    poster_path = models.CharField(max_length=255, blank=True)
    backdrop_path = models.CharField(max_length=255, blank=True)
    release_date = models.DateField(null=True, blank=True)
    runtime = models.PositiveSmallIntegerField(null=True, blank=True)
    vote_average = models.FloatField(null=True, blank=True, help_text="TMDB rating at last sync (0-10).")
    genres = models.JSONField(default=list, blank=True, help_text="Genre names at last sync.")
    synced_at = models.DateTimeField(help_text="When metadata was last refreshed from TMDB.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return f"{self.title} ({self.year})" if self.year else self.title

    def get_absolute_url(self):
        return reverse("movies:detail", kwargs={"tmdb_id": self.tmdb_id})

    @property
    def year(self):
        return self.release_date.year if self.release_date else None

    @property
    def genre_names(self):
        return self.genres or []
