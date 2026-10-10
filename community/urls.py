from django.urls import path

from . import views

app_name = "community"

urlpatterns = [
    path("movies/<int:tmdb_id>/comments/", views.comment_list, name="comment_list"),
    path("movies/<int:tmdb_id>/comments/new/", views.comment_create, name="comment_create"),
    path("movies/<int:tmdb_id>/rate/", views.rate, name="rate"),
    path("movies/<int:tmdb_id>/rate/remove/", views.rate_remove, name="rate_remove"),
    path("movies/<int:tmdb_id>/favorite/", views.favorite, name="favorite"),
    path("movies/<int:tmdb_id>/list/", views.list_status, name="list_status"),
    path("comments/<int:pk>/", views.comment_detail, name="comment_detail"),
    path("comments/<int:pk>/edit/", views.comment_edit, name="comment_edit"),
    path("comments/<int:pk>/delete/", views.comment_delete, name="comment_delete"),
]
