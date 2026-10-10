from django.urls import path

from . import views

app_name = "api"

urlpatterns = [
    path("", views.ApiRootView.as_view(), name="root"),
    path("auth/token/", views.ThrottledTokenObtainPairView.as_view(), name="token_obtain"),
    path("auth/token/refresh/", views.ThrottledTokenRefreshView.as_view(), name="token_refresh"),
    path("auth/token/blacklist/", views.ThrottledTokenBlacklistView.as_view(), name="token_blacklist"),
    path("me/", views.MeView.as_view(), name="me"),
    path("me/favorites/", views.FavoriteListView.as_view(), name="favorites"),
    path("me/favorites/<int:tmdb_id>/", views.FavoriteDetailView.as_view(), name="favorite_detail"),
    path("movies/search/", views.MovieSearchView.as_view(), name="movie_search"),
    path("movies/<int:tmdb_id>/", views.MovieDetailView.as_view(), name="movie_detail"),
    path("movies/<int:tmdb_id>/comments/", views.MovieCommentListView.as_view(), name="movie_comments"),
    path("movies/<int:tmdb_id>/rating/", views.MovieRatingView.as_view(), name="movie_rating"),
    path("comments/<int:pk>/", views.CommentDetailView.as_view(), name="comment_detail"),
    path("users/<str:username>/", views.UserDetailView.as_view(), name="user_detail"),
]
