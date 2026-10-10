from channels.generic.websocket import AsyncWebsocketConsumer

from .realtime import group_name


class MovieCommentsConsumer(AsyncWebsocketConsumer):
    """Pushes live comment changes for one movie to everyone viewing its page.

    Read-only: comments are still created, edited and deleted through the normal HTTP
    endpoints (which enforce authentication, ownership and rate limits). Anything the
    browser sends over the socket is ignored.
    """

    async def connect(self):
        self.group = group_name(self.scope["url_route"]["kwargs"]["tmdb_id"])
        user = self.scope.get("user")
        self.user_id = user.pk if user is not None and user.is_authenticated else None
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if hasattr(self, "group"):
            await self.channel_layer.group_discard(self.group, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        pass  # clients only listen

    async def comment_update(self, event):
        # The author gets the variant with edit/delete buttons; everyone else gets the
        # public one. Both are rendered once by the sender, so no per-viewer queries.
        is_author = self.user_id is not None and self.user_id == event.get("author_id")
        await self.send(text_data=event["owner_html"] if is_author else event["public_html"])
