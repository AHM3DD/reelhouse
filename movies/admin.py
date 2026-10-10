from django.contrib import admin
from django.db.models import Count

from .models import Movie


@admin.register(Movie)
class MovieAdmin(admin.ModelAdmin):
    list_display = ("title", "tmdb_id", "release_date", "vote_average", "comment_count", "rating_count", "synced_at")
    search_fields = ("title", "original_title", "=tmdb_id")
    list_filter = ("release_date", "synced_at")
    readonly_fields = ("created_at", "synced_at")
    date_hierarchy = "release_date"

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _comments=Count("comments", distinct=True), _ratings=Count("ratings", distinct=True)
        )

    @admin.display(description="Comments", ordering="_comments")
    def comment_count(self, obj):
        return obj._comments

    @admin.display(description="Ratings", ordering="_ratings")
    def rating_count(self, obj):
        return obj._ratings
