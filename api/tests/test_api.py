from rest_framework.test import APITestCase

from accounts.models import User
from community.models import Comment, FavoriteMovie, MovieRating
from movies.testing import TMDBMockMixin, detail_payload, list_payload, make_movie, movie_payload

PASSWORD = "Sup3r-Secret-pass"


class APITestBase(TMDBMockMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.alice = User.objects.create_user("alice", "alice@example.com", PASSWORD)
        self.bob = User.objects.create_user("bob", "bob@example.com", PASSWORD)
        self.movie = make_movie()

    def tokens(self, username="alice"):
        response = self.client.post("/api/auth/token/", {"username": username, "password": PASSWORD}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        return response.data

    def auth(self, username="alice"):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.tokens(username)['access']}")


class JWTTests(APITestBase):
    def test_obtain_and_use_token(self):
        tokens = self.tokens()
        self.assertIn("access", tokens)
        self.assertIn("refresh", tokens)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        response = self.client.get("/api/me/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["username"], "alice")

    def test_bad_credentials(self):
        response = self.client.post("/api/auth/token/", {"username": "alice", "password": "nope"}, format="json")
        self.assertEqual(response.status_code, 401)

    def test_refresh_rotates_and_blacklists(self):
        refresh = self.tokens()["refresh"]
        response = self.client.post("/api/auth/token/refresh/", {"refresh": refresh}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertNotEqual(response.data["refresh"], refresh)
        reused = self.client.post("/api/auth/token/refresh/", {"refresh": refresh}, format="json")
        self.assertEqual(reused.status_code, 401, "a rotated refresh token must not be reusable")

    def test_blacklist_logout(self):
        refresh = self.tokens()["refresh"]
        self.assertEqual(self.client.post("/api/auth/token/blacklist/", {"refresh": refresh}, format="json").status_code, 200)
        self.assertEqual(self.client.post("/api/auth/token/refresh/", {"refresh": refresh}, format="json").status_code, 401)

    def test_invalid_token_rejected(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer not-a-token")
        self.assertEqual(self.client.get("/api/me/").status_code, 401)

    def test_protected_endpoints_reject_anonymous(self):
        for method, url in [
            ("get", "/api/me/"),
            ("get", "/api/me/favorites/"),
            ("post", "/api/me/favorites/"),
            ("delete", "/api/me/favorites/27205/"),
            ("put", "/api/movies/27205/rating/"),
            ("post", "/api/movies/27205/comments/"),
        ]:
            response = getattr(self.client, method)(url, {}, format="json")
            self.assertEqual(response.status_code, 401, f"{method} {url}")

    def test_token_endpoint_is_throttled(self):
        for _ in range(10):
            self.client.post("/api/auth/token/", {"username": "alice", "password": "x"}, format="json")
        response = self.client.post("/api/auth/token/", {"username": "alice", "password": PASSWORD}, format="json")
        self.assertEqual(response.status_code, 429)


class CommentAPITests(APITestBase):
    def test_public_can_list_comments(self):
        Comment.objects.create(user=self.alice, movie=self.movie, body="Great")
        response = self.client.get("/api/movies/27205/comments/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"][0]["author"], "alice")
        self.assertNotIn("email", str(response.data))

    def test_create_comment(self):
        self.auth()
        response = self.client.post("/api/movies/27205/comments/", {"body": "  Nice  "}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Comment.objects.get().body, "Nice")

    def test_blank_comment_rejected(self):
        self.auth()
        response = self.client.post("/api/movies/27205/comments/", {"body": "   "}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_cannot_edit_or_delete_others_comments(self):
        comment = Comment.objects.create(user=self.alice, movie=self.movie, body="mine")
        self.auth("bob")
        self.assertEqual(self.client.patch(f"/api/comments/{comment.pk}/", {"body": "x"}, format="json").status_code, 403)
        self.assertEqual(self.client.delete(f"/api/comments/{comment.pk}/").status_code, 403)
        comment.refresh_from_db()
        self.assertEqual(comment.body, "mine")

    def test_owner_can_edit_and_delete(self):
        comment = Comment.objects.create(user=self.alice, movie=self.movie, body="mine")
        self.auth()
        self.assertEqual(self.client.patch(f"/api/comments/{comment.pk}/", {"body": "edited"}, format="json").status_code, 200)
        comment.refresh_from_db()
        self.assertEqual(comment.body, "edited")
        self.assertEqual(self.client.delete(f"/api/comments/{comment.pk}/").status_code, 204)
        self.assertFalse(Comment.objects.exists())


class RatingAPITests(APITestBase):
    def test_put_creates_then_updates(self):
        self.auth()
        self.assertEqual(self.client.put("/api/movies/27205/rating/", {"score": 6}, format="json").status_code, 200)
        response = self.client.put("/api/movies/27205/rating/", {"score": 8}, format="json")
        self.assertEqual(response.data["score"], 8)
        self.assertEqual(response.data["community"], {"avg": 8.0, "count": 1})
        self.assertEqual(MovieRating.objects.count(), 1)

    def test_invalid_scores(self):
        self.auth()
        for bad in (0, 11, "ten", None):
            response = self.client.put("/api/movies/27205/rating/", {"score": bad}, format="json")
            self.assertEqual(response.status_code, 400, bad)

    def test_delete_affects_only_own_rating(self):
        MovieRating.objects.create(user=self.alice, movie=self.movie, score=7)
        self.auth("bob")
        self.assertEqual(self.client.delete("/api/movies/27205/rating/").status_code, 404)
        self.assertTrue(MovieRating.objects.filter(user=self.alice).exists())


class FavoriteAPITests(APITestBase):
    def test_add_is_idempotent_and_remove(self):
        self.auth()
        first = self.client.post("/api/me/favorites/", {"tmdb_id": 27205}, format="json")
        second = self.client.post("/api/me/favorites/", {"tmdb_id": 27205}, format="json")
        self.assertEqual((first.status_code, second.status_code), (201, 200))
        self.assertEqual(FavoriteMovie.objects.count(), 1)
        listing = self.client.get("/api/me/favorites/")
        self.assertEqual(listing.data["results"][0]["movie"]["title"], "Inception")
        self.assertEqual(self.client.delete("/api/me/favorites/27205/").status_code, 204)
        self.assertFalse(FavoriteMovie.objects.exists())

    def test_favorites_are_scoped_to_user(self):
        FavoriteMovie.objects.create(user=self.alice, movie=self.movie)
        self.auth("bob")
        self.assertEqual(self.client.get("/api/me/favorites/").data["count"], 0)
        self.assertEqual(self.client.delete("/api/me/favorites/27205/").status_code, 404)
        self.assertTrue(FavoriteMovie.objects.filter(user=self.alice).exists())

    def test_unknown_movie_rejected(self):
        self.auth()
        response = self.client.post("/api/me/favorites/", {"tmdb_id": 99999999}, format="json")
        self.assertEqual(response.status_code, 404)

    def test_tmdb_outage_returns_503(self):
        self.route("/movie/155", None, status=503)
        self.auth()
        response = self.client.post("/api/me/favorites/", {"tmdb_id": 155}, format="json")
        self.assertEqual(response.status_code, 503)


class MovieAndProfileAPITests(APITestBase):
    def test_movie_search(self):
        self.route("/search/movie", list_payload([movie_payload(438631, "Dune")]))
        response = self.client.get("/api/movies/search/", {"q": "dune"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"][0]["title"], "Dune")
        self.assertEqual(self.client.get("/api/movies/search/").status_code, 400)

    def test_movie_detail_includes_community_stats(self):
        self.route("/movie/27205", detail_payload())
        MovieRating.objects.create(user=self.alice, movie=self.movie, score=10)
        response = self.client.get("/api/movies/27205/")
        self.assertEqual(response.data["title"], "Inception")
        self.assertEqual(response.data["community"], {"avg": 10.0, "count": 1})

    def test_public_profile_hides_email(self):
        response = self.client.get("/api/users/alice/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("email", response.data)

    def test_me_update_bio_only(self):
        self.auth()
        response = self.client.patch("/api/me/", {"bio": "Hi", "username": "hacker", "email": "x@x.com"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.alice.refresh_from_db()
        self.assertEqual(self.alice.username, "alice")
        self.assertEqual(self.alice.email, "alice@example.com")
        self.assertEqual(self.alice.profile.bio, "Hi")
