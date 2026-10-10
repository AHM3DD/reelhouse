from django.conf import settings
from rest_framework import serializers

from accounts.models import User
from community.forms import COMMENT_MAX_LENGTH, normalize_comment
from community.models import Comment, FavoriteMovie, MovieRating, WatchlistEntry
from movies.models import Movie


def image_url(path, size):
    return f"{settings.TMDB['IMAGE_BASE_URL']}/{size}{path}" if path else None


class MovieSnapshotSerializer(serializers.ModelSerializer):
    poster_url = serializers.SerializerMethodField()

    class Meta:
        model = Movie
        fields = ("tmdb_id", "title", "release_date", "poster_url", "vote_average")

    def get_poster_url(self, obj):
        return image_url(obj.poster_path, "w342")


class MovieSummarySerializer(serializers.Serializer):
    """Serializes movies.tmdb.MovieSummary dataclasses (TMDB data, not stored locally)."""

    tmdb_id = serializers.IntegerField()
    title = serializers.CharField()
    original_title = serializers.CharField()
    overview = serializers.CharField()
    release_date = serializers.DateField(allow_null=True)
    vote_average = serializers.FloatField()
    vote_count = serializers.IntegerField()
    poster_url = serializers.SerializerMethodField()
    backdrop_url = serializers.SerializerMethodField()

    def get_poster_url(self, obj):
        return image_url(obj.poster_path, "w342")

    def get_backdrop_url(self, obj):
        return image_url(obj.backdrop_path, "w1280")


class MovieDetailSerializer(MovieSummarySerializer):
    tagline = serializers.CharField()
    runtime = serializers.IntegerField(allow_null=True)
    status = serializers.CharField()
    genres = serializers.ListField(source="genre_names", child=serializers.CharField())
    directors = serializers.SerializerMethodField()
    cast = serializers.SerializerMethodField()

    def get_directors(self, obj):
        return [p.name for p in obj.directors]

    def get_cast(self, obj):
        return [{"name": p.name, "character": p.role} for p in obj.cast]


class UserPublicSerializer(serializers.ModelSerializer):
    avatar_url = serializers.SerializerMethodField()
    bio = serializers.CharField(source="profile.bio", read_only=True)

    class Meta:
        model = User
        fields = ("username", "bio", "avatar_url", "date_joined")

    def get_avatar_url(self, obj):
        profile = getattr(obj, "profile", None)
        if profile and profile.avatar:
            request = self.context.get("request")
            return request.build_absolute_uri(profile.avatar.url) if request else profile.avatar.url
        return None


class MeSerializer(UserPublicSerializer):
    bio = serializers.CharField(source="profile.bio", max_length=500, allow_blank=True, required=False)

    class Meta(UserPublicSerializer.Meta):
        fields = ("id", "username", "email", "bio", "avatar_url", "date_joined")
        read_only_fields = ("id", "username", "email", "date_joined")

    def update(self, instance, validated_data):
        profile_data = validated_data.get("profile", {})
        if "bio" in profile_data:
            instance.profile.bio = profile_data["bio"].strip()
            instance.profile.save(update_fields=["bio", "updated_at"])
        return instance


class CommentSerializer(serializers.ModelSerializer):
    author = serializers.CharField(source="user.username", read_only=True)
    movie = serializers.IntegerField(source="movie.tmdb_id", read_only=True)
    is_edited = serializers.BooleanField(read_only=True)
    body = serializers.CharField(max_length=COMMENT_MAX_LENGTH, trim_whitespace=False)

    class Meta:
        model = Comment
        fields = ("id", "movie", "author", "body", "created_at", "updated_at", "is_edited")
        read_only_fields = ("id", "created_at", "updated_at")

    def validate_body(self, value):
        body = normalize_comment(value)
        if not body:
            raise serializers.ValidationError("Comment cannot be empty.")
        return body


class RatingSerializer(serializers.ModelSerializer):
    movie = serializers.IntegerField(source="movie.tmdb_id", read_only=True)
    score = serializers.IntegerField(min_value=1, max_value=10)

    class Meta:
        model = MovieRating
        fields = ("movie", "score", "created_at", "updated_at")
        read_only_fields = ("created_at", "updated_at")


class FavoriteSerializer(serializers.ModelSerializer):
    movie = MovieSnapshotSerializer(read_only=True)
    tmdb_id = serializers.IntegerField(write_only=True, min_value=1)

    class Meta:
        model = FavoriteMovie
        fields = ("tmdb_id", "movie", "created_at")
        read_only_fields = ("created_at",)


class WatchlistEntrySerializer(serializers.ModelSerializer):
    movie = MovieSnapshotSerializer(read_only=True)

    class Meta:
        model = WatchlistEntry
        fields = ("movie", "status", "updated_at")
