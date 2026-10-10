from django.contrib import admin
from django.utils.text import Truncator

from .models import Comment, FavoriteMovie, MovieRating, WatchlistEntry


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("short_body", "user", "movie", "created_at", "updated_at")
    list_filter = ("created_at",)
    search_fields = ("body", "user__username", "movie__title")
    list_select_related = ("user", "movie")
    autocomplete_fields = ("user", "movie")
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "created_at"

    @admin.display(description="Comment")
    def short_body(self, obj):
        return Truncator(obj.body).chars(80)


@admin.register(MovieRating)
class MovieRatingAdmin(admin.ModelAdmin):
    list_display = ("user", "movie", "score", "updated_at")
    list_filter = ("score", "updated_at")
    search_fields = ("user__username", "movie__title")
    list_select_related = ("user", "movie")
    autocomplete_fields = ("user", "movie")
    readonly_fields = ("created_at", "updated_at")


@admin.register(FavoriteMovie)
class FavoriteMovieAdmin(admin.ModelAdmin):
    list_display = ("user", "movie", "created_at")
    list_filter = ("created_at",)
    search_fields = ("user__username", "movie__title")
    list_select_related = ("user", "movie")
    autocomplete_fields = ("user", "movie")
    readonly_fields = ("created_at",)


@admin.register(WatchlistEntry)
class WatchlistEntryAdmin(admin.ModelAdmin):
    list_display = ("user", "movie", "status", "updated_at")
    list_filter = ("status", "updated_at")
    search_fields = ("user__username", "movie__title")
    list_select_related = ("user", "movie")
    autocomplete_fields = ("user", "movie")
    readonly_fields = ("created_at", "updated_at")
