from django.urls import path

from . import consumers

websocket_urlpatterns = [
    path("ws/movies/<int:tmdb_id>/comments/", consumers.MovieCommentsConsumer.as_asgi()),
]
