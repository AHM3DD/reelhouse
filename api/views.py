from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.exceptions import APIException, NotFound
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenBlacklistView, TokenObtainPairView, TokenRefreshView

from accounts.models import User
from community import services
from community.models import Comment, FavoriteMovie, MovieRating
from movies import tmdb
from movies.models import Movie
from movies.services import MovieUnavailable, ensure_movie

from .serializers import (
    CommentSerializer,
    FavoriteSerializer,
    MeSerializer,
    MovieDetailSerializer,
    MovieSummarySerializer,
    RatingSerializer,
    UserPublicSerializer,
)


class ServiceUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "Movie data is temporarily unavailable. Please retry shortly."
    default_code = "tmdb_unavailable"


class IsOwnerOrReadOnly(permissions.BasePermission):
    message = "You can only modify your own content."

    def has_object_permission(self, request, view, obj):
        return request.method in permissions.SAFE_METHODS or obj.user_id == request.user.pk


class CommentCreateThrottle(UserRateThrottle):
    """Throttle only comment creation (scope 'comments'), not reads."""

    scope = "comments"

    def allow_request(self, request, view):
        if request.method != "POST":
            return True
        return super().allow_request(request, view)


def _movie_or_error(tmdb_id):
    try:
        return ensure_movie(tmdb_id)
    except Http404:
        raise NotFound("Movie not found on TMDB.")
    except MovieUnavailable:
        raise ServiceUnavailable()


# --- Auth ----------------------------------------------------------------------------


class ThrottledTokenObtainPairView(TokenObtainPairView):
    throttle_scope = "auth"


class ThrottledTokenRefreshView(TokenRefreshView):
    throttle_scope = "auth"


class ThrottledTokenBlacklistView(TokenBlacklistView):
    throttle_scope = "auth"


# --- Index ---------------------------------------------------------------------------


class ApiRootView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        def url(name, **kwargs):
            return reverse(name, kwargs=kwargs, request=request)

        return Response(
            {
                "auth": {
                    "obtain_token": url("api:token_obtain"),
                    "refresh_token": url("api:token_refresh"),
                    "blacklist_token": url("api:token_blacklist"),
                },
                "me": url("api:me"),
                "my_favorites": url("api:favorites"),
                "movie_search": url("api:movie_search") + "?q=inception",
                "movie_detail": url("api:movie_detail", tmdb_id=27205),
                "movie_comments": url("api:movie_comments", tmdb_id=27205),
                "movie_rating": url("api:movie_rating", tmdb_id=27205),
                "public_profile": url("api:user_detail", username="example"),
            }
        )


# --- Movies (TMDB-backed, public) ----------------------------------------------------


class MovieSearchView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        query = request.query_params.get("q", "").strip()
        if not query:
            return Response({"detail": "Provide a search query with ?q="}, status=status.HTTP_400_BAD_REQUEST)
        try:
            page = tmdb.search(query, tmdb.clamp_page(request.query_params.get("page")))
        except tmdb.TMDBError:
            raise ServiceUnavailable()
        return Response(
            {
                "page": page.page,
                "total_pages": page.total_pages,
                "total_results": page.total_results,
                "results": MovieSummarySerializer(page.results, many=True).data,
            }
        )


class MovieDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, tmdb_id):
        try:
            info = tmdb.movie_detail(tmdb_id)
        except tmdb.TMDBNotFound:
            raise NotFound("Movie not found on TMDB.")
        except tmdb.TMDBError:
            raise ServiceUnavailable()
        movie = Movie.objects.filter(tmdb_id=tmdb_id).first()
        data = MovieDetailSerializer(info).data
        data["community"] = services.community_stats(movie)
        return Response(data)


# --- Comments --------------------------------------------------------------------------


class MovieCommentListView(generics.ListCreateAPIView):
    serializer_class = CommentSerializer
    throttle_classes = [AnonRateThrottle, UserRateThrottle, CommentCreateThrottle]

    def get_permissions(self):
        return [AllowAny()] if self.request.method == "GET" else [IsAuthenticated()]

    def get_queryset(self):
        return Comment.objects.filter(movie__tmdb_id=self.kwargs["tmdb_id"]).select_related("user", "movie")

    def perform_create(self, serializer):
        # Go through the service so API comments are broadcast live like website ones.
        movie = _movie_or_error(self.kwargs["tmdb_id"])
        serializer.instance = services.create_comment(self.request.user, movie, serializer.validated_data["body"])


class CommentDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = CommentSerializer
    queryset = Comment.objects.select_related("user", "movie")
    http_method_names = ["get", "patch", "put", "delete", "head", "options"]

    def get_permissions(self):
        if self.request.method in permissions.SAFE_METHODS:
            return [AllowAny()]
        return [IsAuthenticated(), IsOwnerOrReadOnly()]

    def perform_update(self, serializer):
        if "body" in serializer.validated_data:
            services.update_comment(serializer.instance, self.request.user, serializer.validated_data["body"])

    def perform_destroy(self, instance):
        services.delete_comment(instance, self.request.user)


# --- Ratings ---------------------------------------------------------------------------


class MovieRatingView(APIView):
    """The authenticated user's own rating for a movie: GET / PUT {score} / DELETE."""

    def get(self, request, tmdb_id):
        rating = get_object_or_404(MovieRating.objects.select_related("movie"), user=request.user, movie__tmdb_id=tmdb_id)
        return Response(RatingSerializer(rating).data)

    def put(self, request, tmdb_id):
        serializer = RatingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        movie = _movie_or_error(tmdb_id)
        rating = services.set_rating(request.user, movie, serializer.validated_data["score"])
        data = RatingSerializer(rating).data
        data["community"] = services.community_stats(movie)
        return Response(data)

    def delete(self, request, tmdb_id):
        movie = get_object_or_404(Movie, tmdb_id=tmdb_id)
        if not services.remove_rating(request.user, movie):
            raise NotFound("You have not rated this movie.")
        return Response(status=status.HTTP_204_NO_CONTENT)


# --- Favorites -------------------------------------------------------------------------


class FavoriteListView(generics.ListCreateAPIView):
    """List or add favorites. Always scoped to the authenticated user."""

    serializer_class = FavoriteSerializer

    def get_queryset(self):
        return FavoriteMovie.objects.filter(user=self.request.user).select_related("movie")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        movie = _movie_or_error(serializer.validated_data["tmdb_id"])
        favorite, created = services.add_favorite(request.user, movie)
        return Response(
            FavoriteSerializer(favorite).data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )


class FavoriteDetailView(APIView):
    def delete(self, request, tmdb_id):
        movie = get_object_or_404(Movie, tmdb_id=tmdb_id)
        if not services.remove_favorite(request.user, movie):
            raise NotFound("This movie is not in your favorites.")
        return Response(status=status.HTTP_204_NO_CONTENT)


# --- Users -----------------------------------------------------------------------------


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = MeSerializer
    http_method_names = ["get", "patch", "head", "options"]

    def get_object(self):
        return User.objects.select_related("profile").get(pk=self.request.user.pk)


class UserDetailView(generics.RetrieveAPIView):
    serializer_class = UserPublicSerializer
    permission_classes = [AllowAny]
    queryset = User.objects.filter(is_active=True).select_related("profile")
    lookup_field = "username"

    def retrieve(self, request, *args, **kwargs):
        user = self.get_object()
        data = self.get_serializer(user).data
        data["stats"] = services.profile_stats(user)
        data["favorites"] = [
            {"tmdb_id": f.movie.tmdb_id, "title": f.movie.title}
            for f in services.collection_queryset(user, "favorites")[:20]
        ]
        return Response(data)
