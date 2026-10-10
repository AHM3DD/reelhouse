"""Broadcast comment changes to the movie's WebSocket group.

Messages are HTMX out-of-band fragments: the browser's htmx WebSocket extension swaps
them straight into the page. Broadcasting happens after the database transaction
commits, and a Redis outage never breaks commenting: the change is saved and other
viewers simply see it on their next page load.
"""
import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth.models import AnonymousUser
from django.db import transaction
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


def group_name(tmdb_id):
    return f"movie-comments-{int(tmdb_id)}"


def _render_comment(comment, viewer):
    # csrf_token "NOTPROVIDED" renders nothing; HTMX sends the page's token in a header.
    return render_to_string(
        "community/partials/comment.html", {"comment": comment, "user": viewer, "csrf_token": "NOTPROVIDED"}
    )


def _count_html(count):
    return render_to_string("community/partials/comment_count.html", {"comment_count": count, "oob": True})


def _created_html(comment, viewer, count):
    return (
        '<div hx-swap-oob="afterbegin:#comment-list">' + _render_comment(comment, viewer) + "</div>"
        '<div id="comments-empty" hx-swap-oob="delete"></div>' + _count_html(count)
    )


def _edited_html(comment, viewer):
    return f'<div hx-swap-oob="outerHTML:#comment-{comment.pk}">' + _render_comment(comment, viewer) + "</div>"


def _deleted_html(comment_id, count):
    # comment_deleted.html updates the count and shows the empty state when count is 0.
    return f'<div id="comment-{comment_id}" hx-swap-oob="delete"></div>' + render_to_string(
        "community/partials/comment_deleted.html", {"comment_count": count}
    )


def _send(tmdb_id, payload):
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    try:
        async_to_sync(channel_layer.group_send)(group_name(tmdb_id), {"type": "comment.update", **payload})
    except Exception as exc:  # noqa: BLE001 - live updates are best effort
        logger.warning("Live comment broadcast failed: %s", type(exc).__name__)


def broadcast_comment(action, comment, count):
    """action: 'created' or 'edited'. Call after the comment is saved."""
    tmdb_id = comment.movie.tmdb_id
    anonymous = AnonymousUser()
    if action == "created":
        public_html = _created_html(comment, anonymous, count)
        owner_html = _created_html(comment, comment.user, count)
    else:
        public_html = _edited_html(comment, anonymous)
        owner_html = _edited_html(comment, comment.user)
    payload = {"author_id": comment.user_id, "public_html": public_html, "owner_html": owner_html}
    transaction.on_commit(lambda: _send(tmdb_id, payload))


def broadcast_deletion(tmdb_id, comment_id, count):
    html = _deleted_html(comment_id, count)
    payload = {"author_id": None, "public_html": html, "owner_html": html}
    transaction.on_commit(lambda: _send(tmdb_id, payload))
