from django.db import IntegrityError, transaction
from django.urls import reverse

from accounts.models import User
from community import services
from community.models import Comment, FavoriteMovie, MovieRating, WatchlistEntry
from movies.models import Movie
from movies.testing import TMDBTestCase, detail_payload, make_movie

HX = {"HTTP_HX_REQUEST": "true"}


class CommunityTestCase(TMDBTestCase):
    def setUp(self):
        super().setUp()
        self.alice = User.objects.create_user("alice", "alice@example.com", "pw-Secret-123")
        self.bob = User.objects.create_user("bob", "bob@example.com", "pw-Secret-123")
        self.movie = make_movie()


class CommentTests(CommunityTestCase):
    def create_url(self, tmdb_id=27205):
        return reverse("community:comment_create", args=[tmdb_id])

    def test_logged_in_user_can_comment(self):
        self.client.force_login(self.alice)
        response = self.client.post(self.create_url(), {"body": "  Loved the ending!  "}, **HX)
        self.assertEqual(response.status_code, 200)
        comment = Comment.objects.get()
        self.assertEqual(comment.body, "Loved the ending!")
        self.assertEqual(comment.user, self.alice)
        self.assertContains(response, "Loved the ending!")
        self.assertContains(response, "Your comment was posted.")  # OOB toast

    def test_comment_on_unsaved_movie_creates_snapshot_from_tmdb(self):
        self.route("/movie/155", detail_payload(155, "The Dark Knight"))
        self.client.force_login(self.alice)
        self.client.post(self.create_url(155), {"body": "Why so serious?"})
        self.assertEqual(Movie.objects.get(tmdb_id=155).title, "The Dark Knight")

    def test_comment_on_nonexistent_movie_is_rejected(self):
        self.client.force_login(self.alice)
        response = self.client.post(self.create_url(99999999), {"body": "hello"})
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Comment.objects.exists())

    def test_anonymous_user_must_log_in(self):
        response = self.client.post(self.create_url(), {"body": "hi"})
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])
        response = self.client.post(self.create_url(), {"body": "hi"}, **HX)
        self.assertEqual(response.status_code, 204)
        self.assertIn(reverse("accounts:login"), response["HX-Redirect"])
        self.assertFalse(Comment.objects.exists())

    def test_empty_comment_is_rejected(self):
        self.client.force_login(self.alice)
        response = self.client.post(self.create_url(), {"body": "   \n\n  "}, **HX)
        self.assertContains(response, "Comment cannot be empty.")
        self.assertFalse(Comment.objects.exists())

    def test_overlong_comment_is_rejected(self):
        self.client.force_login(self.alice)
        self.client.post(self.create_url(), {"body": "x" * 2001}, **HX)
        self.assertFalse(Comment.objects.exists())

    def test_comment_html_is_escaped(self):
        self.client.force_login(self.alice)
        self.client.post(self.create_url(), {"body": "<script>alert('x')</script>"})
        self.route("/movie/27205", detail_payload())
        response = self.client.get(reverse("movies:detail", args=[27205]))
        self.assertNotContains(response, "<script>alert('x')</script>")
        self.assertContains(response, "&lt;script&gt;alert(&#x27;x&#x27;)&lt;/script&gt;")

    def test_get_is_not_allowed_for_create(self):
        self.client.force_login(self.alice)
        self.assertEqual(self.client.get(self.create_url()).status_code, 405)

    def test_author_can_edit_comment(self):
        comment = Comment.objects.create(user=self.alice, movie=self.movie, body="first")
        self.client.force_login(self.alice)
        response = self.client.post(reverse("community:comment_edit", args=[comment.pk]), {"body": "edited"}, **HX)
        self.assertEqual(response.status_code, 200)
        comment.refresh_from_db()
        self.assertEqual(comment.body, "edited")

    def test_user_cannot_edit_someone_elses_comment(self):
        comment = Comment.objects.create(user=self.alice, movie=self.movie, body="mine")
        self.client.force_login(self.bob)
        url = reverse("community:comment_edit", args=[comment.pk])
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url, {"body": "hacked"}).status_code, 403)
        comment.refresh_from_db()
        self.assertEqual(comment.body, "mine")

    def test_user_cannot_delete_someone_elses_comment(self):
        comment = Comment.objects.create(user=self.alice, movie=self.movie, body="mine")
        self.client.force_login(self.bob)
        response = self.client.post(reverse("community:comment_delete", args=[comment.pk]), **HX)
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Comment.objects.filter(pk=comment.pk).exists())

    def test_author_can_delete_comment(self):
        comment = Comment.objects.create(user=self.alice, movie=self.movie, body="mine")
        self.client.force_login(self.alice)
        response = self.client.post(reverse("community:comment_delete", args=[comment.pk]), **HX)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Comment.objects.filter(pk=comment.pk).exists())
        self.assertContains(response, "0 comments")
        self.assertContains(response, "No comments yet")

    def test_edit_buttons_only_shown_to_author(self):
        Comment.objects.create(user=self.alice, movie=self.movie, body="mine")
        self.route("/movie/27205", detail_payload())
        self.client.force_login(self.bob)
        response = self.client.get(reverse("movies:detail", args=[27205]))
        self.assertContains(response, "mine")
        self.assertNotContains(response, 'aria-label="Edit comment"')

    def test_comments_are_paginated(self):
        Comment.objects.bulk_create([Comment(user=self.alice, movie=self.movie, body=f"c{i}") for i in range(13)])
        self.route("/movie/27205", detail_payload())
        response = self.client.get(reverse("movies:detail", args=[27205]))
        self.assertContains(response, "Load more comments")
        self.assertContains(response, "13 comments")
        more = self.client.get(reverse("community:comment_list", args=[27205]), {"page": 2}, **HX)
        self.assertEqual(more.content.decode().count('class="card scroll-mt-24'), 3)

    def test_comment_rate_limit(self):
        self.client.force_login(self.alice)
        for i in range(6):
            self.client.post(self.create_url(), {"body": f"comment {i}"}, **HX)
        response = self.client.post(self.create_url(), {"body": "one too many"}, **HX)
        self.assertEqual(response.status_code, 429)
        self.assertEqual(Comment.objects.count(), 6)

    def test_empty_body_db_constraint(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Comment.objects.create(user=self.alice, movie=self.movie, body="")


class RatingTests(CommunityTestCase):
    def rate(self, score, user=None, **extra):
        self.client.force_login(user or self.alice)
        return self.client.post(reverse("community:rate", args=[27205]), {"score": score}, **extra)

    def test_user_can_rate_and_update(self):
        self.rate(7)
        self.rate(9)
        self.assertEqual(MovieRating.objects.get(user=self.alice, movie=self.movie).score, 9)
        self.assertEqual(MovieRating.objects.count(), 1)

    def test_invalid_scores_are_rejected(self):
        for bad in ("0", "11", "-1", "abc", "7.5", ""):
            response = self.rate(bad, **HX)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "field-error")
        self.assertFalse(MovieRating.objects.exists())

    def test_average_updates_after_change_and_removal(self):
        self.rate(8)
        response = self.rate(4, user=self.bob, **HX)
        self.assertContains(response, "6.0")
        self.assertContains(response, "2 ratings")
        self.client.post(reverse("community:rate_remove", args=[27205]), **HX)
        self.assertEqual(services.community_stats(self.movie), {"avg": 8.0, "count": 1})

    def test_removal_only_affects_own_rating(self):
        MovieRating.objects.create(user=self.alice, movie=self.movie, score=10)
        self.client.force_login(self.bob)
        self.client.post(reverse("community:rate_remove", args=[27205]))
        self.assertTrue(MovieRating.objects.filter(user=self.alice).exists())

    def test_anonymous_cannot_rate(self):
        response = self.client.post(reverse("community:rate", args=[27205]), {"score": 5})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(MovieRating.objects.exists())

    def test_duplicate_rating_rejected_by_database(self):
        MovieRating.objects.create(user=self.alice, movie=self.movie, score=5)
        with self.assertRaises(IntegrityError), transaction.atomic():
            MovieRating.objects.create(user=self.alice, movie=self.movie, score=6)

    def test_score_range_enforced_by_database(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            MovieRating.objects.create(user=self.alice, movie=self.movie, score=11)

    def test_service_rejects_invalid_score(self):
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            services.set_rating(self.alice, self.movie, 0)


class FavoriteTests(CommunityTestCase):
    def post(self, action, user=None, tmdb_id=27205, **extra):
        self.client.force_login(user or self.alice)
        return self.client.post(
            reverse("community:favorite", args=[tmdb_id]), {"action": action, "variant": "detail"}, **extra
        )

    def test_add_and_remove_favorite(self):
        response = self.post("add", **HX)
        self.assertContains(response, "In favorites")
        self.assertTrue(FavoriteMovie.objects.filter(user=self.alice, movie=self.movie).exists())
        response = self.post("remove", **HX)
        self.assertContains(response, "Add to favorites")
        self.assertFalse(FavoriteMovie.objects.exists())

    def test_adding_twice_does_not_duplicate(self):
        self.post("add")
        self.post("add")
        self.assertEqual(FavoriteMovie.objects.count(), 1)

    def test_cannot_remove_another_users_favorite(self):
        FavoriteMovie.objects.create(user=self.alice, movie=self.movie)
        self.post("remove", user=self.bob)
        self.assertTrue(FavoriteMovie.objects.filter(user=self.alice).exists())

    def test_invalid_action_rejected(self):
        response = self.post("explode")
        self.assertEqual(response.status_code, 400)

    def test_duplicate_favorite_rejected_by_database(self):
        FavoriteMovie.objects.create(user=self.alice, movie=self.movie)
        with self.assertRaises(IntegrityError), transaction.atomic():
            FavoriteMovie.objects.create(user=self.alice, movie=self.movie)

    def test_anonymous_htmx_request_redirects_to_login(self):
        response = self.client.post(
            reverse("community:favorite", args=[27205]), {"action": "add"},
            HTTP_HX_REQUEST="true", HTTP_HX_CURRENT_URL="http://testserver/movies/27205/",
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response["HX-Redirect"], "/accounts/login/?next=%2Fmovies%2F27205%2F")


class WatchlistTests(CommunityTestCase):
    def test_set_and_clear_status(self):
        self.client.force_login(self.alice)
        url = reverse("community:list_status", args=[27205])
        self.client.post(url, {"status": "want"}, **HX)
        self.assertEqual(WatchlistEntry.objects.get().status, "want")
        response = self.client.post(url, {"status": "watched"}, **HX)
        self.assertContains(response, "Watched")
        self.assertEqual(WatchlistEntry.objects.get().status, "watched")
        self.client.post(url, {"status": "none"}, **HX)
        self.assertFalse(WatchlistEntry.objects.exists())

    def test_invalid_status_rejected(self):
        self.client.force_login(self.alice)
        response = self.client.post(reverse("community:list_status", args=[27205]), {"status": "maybe"})
        self.assertEqual(response.status_code, 400)
