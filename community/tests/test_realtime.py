from unittest import mock

from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.test import TransactionTestCase

from accounts.models import User
from community import services
from config.asgi import application
from movies.testing import make_movie

ORIGIN = (b"origin", b"http://testserver")


class LiveCommentTests(TransactionTestCase):
    """WebSocket broadcasting of comment changes (in-memory channel layer in tests)."""

    def setUp(self):
        self.alice = User.objects.create_user("alice", "alice@example.com", "pw-Secret-123")
        self.bob = User.objects.create_user("bob", "bob@example.com", "pw-Secret-123")
        self.movie = make_movie()
        self.other_movie = make_movie(tmdb_id=155, title="The Dark Knight")
        self.client.force_login(self.alice)
        self.alice_cookie = f"sessionid={self.client.cookies['sessionid'].value}".encode()

    async def connect(self, tmdb_id=27205, cookie=None, origin=ORIGIN):
        headers = [origin] + ([(b"cookie", cookie)] if cookie else [])
        communicator = WebsocketCommunicator(application, f"/ws/movies/{tmdb_id}/comments/", headers=headers)
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        return communicator

    async def test_new_comment_reaches_viewers_with_correct_controls(self):
        viewer = await self.connect()
        author = await self.connect(cookie=self.alice_cookie)

        await database_sync_to_async(services.create_comment)(self.alice, self.movie, "Live from the cinema")

        public = await viewer.receive_from(timeout=2)
        own = await author.receive_from(timeout=2)
        for message in (public, own):
            self.assertIn('hx-swap-oob="afterbegin:#comment-list"', message)
            self.assertIn("Live from the cinema", message)
            self.assertIn('id="comments-empty" hx-swap-oob="delete"', message)
            self.assertIn("1 comment<", message)
        self.assertNotIn('aria-label="Edit comment"', public)
        self.assertIn('aria-label="Edit comment"', own)
        await viewer.disconnect()
        await author.disconnect()

    async def test_comment_text_is_escaped(self):
        viewer = await self.connect()
        await database_sync_to_async(services.create_comment)(self.alice, self.movie, "<script>alert(1)</script>")
        message = await viewer.receive_from(timeout=2)
        self.assertNotIn("<script>", message)
        self.assertIn("&lt;script&gt;", message)
        await viewer.disconnect()

    async def test_edit_and_delete_are_broadcast(self):
        comment = await database_sync_to_async(services.create_comment)(self.alice, self.movie, "First take")
        viewer = await self.connect()

        await database_sync_to_async(services.update_comment)(comment, self.alice, "Second take")
        edited = await viewer.receive_from(timeout=2)
        self.assertIn(f'hx-swap-oob="outerHTML:#comment-{comment.pk}"', edited)
        self.assertIn("Second take", edited)

        comment_id = comment.pk  # Django clears pk on delete
        await database_sync_to_async(services.delete_comment)(comment, self.alice)
        deleted = await viewer.receive_from(timeout=2)
        self.assertIn(f'id="comment-{comment_id}" hx-swap-oob="delete"', deleted)
        self.assertIn("0 comments", deleted)
        self.assertIn("No comments yet", deleted)
        await viewer.disconnect()

    async def test_updates_are_scoped_to_the_movie(self):
        other_viewer = await self.connect(tmdb_id=155)
        await database_sync_to_async(services.create_comment)(self.bob, self.movie, "Only for Inception")
        self.assertTrue(await other_viewer.receive_nothing(timeout=0.3))
        await other_viewer.disconnect()

    async def test_client_messages_are_ignored(self):
        viewer = await self.connect()
        await viewer.send_to(text_data='<div id="comment-list" hx-swap-oob="true">hijack</div>')
        self.assertTrue(await viewer.receive_nothing(timeout=0.3))
        await viewer.disconnect()

    async def test_foreign_origin_is_rejected(self):
        communicator = WebsocketCommunicator(
            application, "/ws/movies/27205/comments/", headers=[(b"origin", b"https://evil.example")]
        )
        connected, _ = await communicator.connect()
        self.assertFalse(connected)
        await communicator.disconnect()

    async def test_redis_outage_does_not_break_commenting(self):
        failing_layer = mock.Mock()
        failing_layer.group_send = mock.AsyncMock(side_effect=ConnectionError("redis down"))
        with mock.patch("community.realtime.get_channel_layer", return_value=failing_layer):
            comment = await database_sync_to_async(services.create_comment)(self.alice, self.movie, "Still saved")
        self.assertTrue(await database_sync_to_async(type(comment).objects.filter(pk=comment.pk).exists)())
