from django.urls import path

from . import views

app_name = "movies"

urlpatterns = [
    path("", views.home, name="home"),
    path("movies/", views.browse, name="browse"),
    path("movies/c/<slug:slug>/", views.category, name="category"),
    path("movies/<int:tmdb_id>/", views.detail, name="detail"),
    path("search/", views.search, name="search"),
]
