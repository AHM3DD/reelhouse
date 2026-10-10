import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from accounts.models import User, UserProfile
from community.models import FavoriteMovie, MovieRating
from movies.testing import TMDBMockMixin, make_movie

PASSWORD = "Sup3r-Secret-pass"


def image_file(name="avatar.png", fmt="PNG", size=(600, 300)):
    buffer = io.BytesIO()
    Image.new("RGB", size, (200, 30, 30)).save(buffer, format=fmt)
    return SimpleUploadedFile(name, buffer.getvalue(), content_type=f"image/{fmt.lower()}")


class AccountsTestCase(TMDBMockMixin, TestCase):
    pass


class RegistrationTests(AccountsTestCase):
    url = reverse("accounts:register")

    def data(self, **overrides):
        data = {"username": "newbie", "email": "New@Example.com", "password1": PASSWORD, "password2": PASSWORD}
        data.update(overrides)
        return data

    def test_registration_creates_user_profile_and_logs_in(self):
        response = self.client.post(self.url, self.data())
        self.assertRedirects(response, reverse("movies:home"), fetch_redirect_response=False)
        user = User.objects.get(username="newbie")
        self.assertEqual(user.email, "new@example.com")  # normalised
        self.assertTrue(UserProfile.objects.filter(user=user).exists())
        self.assertNotEqual(user.password, PASSWORD)  # hashed
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_registration_honours_safe_next_only(self):
        response = self.client.post(self.url + "?next=/movies/27205/", self.data(next="/movies/27205/"))
        self.assertEqual(response["Location"], "/movies/27205/")
        self.client.logout()
        response = self.client.post(self.url, self.data(username="other", email="o@example.com", next="https://evil.example/"))
        self.assertEqual(response["Location"], reverse("movies:home"))

    def test_duplicate_username_rejected_case_insensitively(self):
        User.objects.create_user("Newbie", "first@example.com", PASSWORD)
        response = self.client.post(self.url, self.data())
        self.assertContains(response, "already taken")
        self.assertEqual(User.objects.count(), 1)

    def test_duplicate_email_rejected_case_insensitively(self):
        User.objects.create_user("first", "new@example.com", PASSWORD)
        response = self.client.post(self.url, self.data(email="NEW@example.COM"))
        self.assertContains(response, "already exists")
        self.assertEqual(User.objects.count(), 1)

    def test_invalid_input_rejected(self):
        cases = [
            self.data(password2="different-Pass-1"),
            self.data(password1="123", password2="123"),
            self.data(email="not-an-email"),
            self.data(username="a b<script>"),
            self.data(username=""),
        ]
        for data in cases:
            response = self.client.post(self.url, data)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "field-error")
        self.assertFalse(User.objects.exists())

    def test_email_uniqueness_enforced_by_database(self):
        User.objects.create_user("one", "same@example.com", PASSWORD)
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user("two", "SAME@example.com", PASSWORD)


class LoginLogoutTests(AccountsTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user("cinephile", "cine@example.com", PASSWORD)

    def test_login_with_username_or_email(self):
        for identifier in ("cinephile", "CINE@example.com"):
            response = self.client.post(reverse("accounts:login"), {"username": identifier, "password": PASSWORD})
            self.assertEqual(response.status_code, 302, identifier)
            self.client.logout()

    def test_invalid_credentials_show_error(self):
        response = self.client.post(reverse("accounts:login"), {"username": "cinephile", "password": "wrong"})
        self.assertContains(response, "combination is not correct")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_login_rejects_unsafe_next(self):
        response = self.client.post(
            reverse("accounts:login"), {"username": "cinephile", "password": PASSWORD, "next": "https://evil.example/"}
        )
        self.assertEqual(response["Location"], reverse("movies:home"))

    def test_logout_requires_post(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("accounts:logout")).status_code, 405)
        response = self.client.post(reverse("accounts:logout"))
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_login_is_rate_limited(self):
        for _ in range(10):
            self.client.post(reverse("accounts:login"), {"username": "cinephile", "password": "wrong"})
        response = self.client.post(reverse("accounts:login"), {"username": "cinephile", "password": PASSWORD})
        self.assertEqual(response.status_code, 429)

    def test_protected_pages_redirect_to_login(self):
        for name in ("accounts:collection", "accounts:profile_edit", "accounts:password_change"):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 302)
            self.assertIn(reverse("accounts:login"), response["Location"])


class ProfileTests(AccountsTestCase):
    def setUp(self):
        super().setUp()
        self.alice = User.objects.create_user("alice", "alice@example.com", PASSWORD)
        self.bob = User.objects.create_user("bob", "bob@example.com", PASSWORD)

    def test_public_profile_hides_email(self):
        movie = make_movie()
        FavoriteMovie.objects.create(user=self.alice, movie=movie)
        MovieRating.objects.create(user=self.alice, movie=movie, score=9)
        response = self.client.get(reverse("accounts:profile", args=["alice"]))
        self.assertContains(response, "alice")
        self.assertContains(response, "Inception")
        self.assertNotContains(response, "alice@example.com")

    def test_profile_tabs_and_empty_states(self):
        response = self.client.get(reverse("accounts:profile", args=["bob"]), {"tab": "ratings"})
        self.assertContains(response, "No ratings yet")
        response = self.client.get(
            reverse("accounts:profile", args=["bob"]), {"tab": "comments"},
            HTTP_HX_REQUEST="true", HTTP_HX_TARGET="profile-tab",
        )
        self.assertNotContains(response, "<html")
        self.assertContains(response, "No comments yet")

    def test_profile_username_is_case_insensitive(self):
        response = self.client.get(reverse("accounts:profile", args=["ALICE"]))
        self.assertRedirects(response, reverse("accounts:profile", args=["alice"]), status_code=301)

    def test_unknown_profile_404(self):
        self.assertEqual(self.client.get(reverse("accounts:profile", args=["ghost"])).status_code, 404)

    def test_user_edits_only_own_profile(self):
        self.client.force_login(self.bob)
        self.client.post(reverse("accounts:profile_edit"), {"bio": "Bob's bio", "user": self.alice.pk})
        self.alice.profile.refresh_from_db()
        self.bob.profile.refresh_from_db()
        self.assertEqual(self.alice.profile.bio, "")
        self.assertEqual(self.bob.profile.bio, "Bob's bio")

    def test_avatar_upload_is_processed(self):
        self.client.force_login(self.alice)
        response = self.client.post(reverse("accounts:profile_edit"), {"bio": "", "avatar": image_file()})
        self.assertEqual(response.status_code, 302)
        self.alice.profile.refresh_from_db()
        self.assertTrue(self.alice.profile.avatar.name.endswith(".webp"))
        with Image.open(self.alice.profile.avatar.path) as img:
            self.assertEqual(img.size, (400, 400))

    def test_avatar_rejects_non_images(self):
        self.client.force_login(self.alice)
        fake = SimpleUploadedFile("evil.png", b"<?php echo 'hi'; ?>", content_type="image/png")
        response = self.client.post(reverse("accounts:profile_edit"), {"bio": "", "avatar": fake})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "field-error")
        self.alice.profile.refresh_from_db()
        self.assertFalse(self.alice.profile.avatar)

    @override_settings(AVATAR_MAX_UPLOAD_BYTES=1000)
    def test_avatar_rejects_large_files(self):
        self.client.force_login(self.alice)
        response = self.client.post(reverse("accounts:profile_edit"), {"bio": "", "avatar": image_file(size=(800, 800))})
        self.assertContains(response, "or smaller")

    def test_avatar_removal(self):
        self.client.force_login(self.alice)
        self.client.post(reverse("accounts:profile_edit"), {"bio": "", "avatar": image_file()})
        self.client.post(reverse("accounts:profile_edit"), {"bio": "", "remove_avatar": "on"})
        self.alice.profile.refresh_from_db()
        self.assertFalse(self.alice.profile.avatar)

    def test_collection_page(self):
        movie = make_movie()
        FavoriteMovie.objects.create(user=self.alice, movie=movie)
        self.client.force_login(self.alice)
        response = self.client.get(reverse("accounts:collection"))
        self.assertContains(response, "My collection")
        self.assertContains(response, "Inception")
