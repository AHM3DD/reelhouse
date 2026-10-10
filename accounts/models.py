import hashlib
import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Lower
from django.urls import reverse


class User(AbstractUser):
    """Django's standard user, with a required email that is unique case-insensitively."""

    email = models.EmailField("email address")

    class Meta:
        constraints = [
            models.UniqueConstraint(Lower("email"), name="accounts_user_email_ci_unique"),
            models.UniqueConstraint(Lower("username"), name="accounts_user_username_ci_unique"),
        ]

    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("accounts:profile", kwargs={"username": self.username})


def avatar_upload_to(instance, filename):
    # Ignore the client-supplied name; avatars are always re-encoded to WebP.
    return f"avatars/{instance.user_id}/{uuid.uuid4().hex}.webp"


class UserProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    bio = models.TextField(max_length=500, blank=True)
    avatar = models.ImageField(upload_to=avatar_upload_to, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Profile of {self.user.username}"

    @property
    def avatar_hue(self):
        """Stable colour for the initials fallback avatar."""
        return int(hashlib.md5(self.user.username.encode()).hexdigest()[:4], 16) % 360

    @property
    def initial(self):
        return self.user.username[:1].upper()
