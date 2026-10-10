from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm, UserCreationForm
from django.core.files.uploadedfile import UploadedFile
from django.core.validators import RegexValidator

from core.forms import StyledFormMixin

from .models import UserProfile
from .services import process_avatar

User = get_user_model()

username_validator = RegexValidator(
    r"^[A-Za-z0-9_.-]{3,30}$",
    "Use 3-30 characters: letters, numbers, underscores, dots or hyphens.",
)


class RegistrationForm(StyledFormMixin, UserCreationForm):
    email = forms.EmailField(
        max_length=254,
        widget=forms.EmailInput(attrs={"autocomplete": "email", "placeholder": "you@example.com"}),
    )

    class Meta:
        model = User
        fields = ("username", "email")
        widgets = {
            "username": forms.TextInput(attrs={"autocomplete": "username", "placeholder": "cinephile42"}),
        }
        help_texts = {"username": "3-30 characters. Letters, numbers, _ . - only."}

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        username_validator(username)
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("That username is already taken.")
        return username

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email address already exists.")
        return email


class LoginForm(StyledFormMixin, AuthenticationForm):
    username = forms.CharField(
        label="Username or email",
        max_length=254,
        widget=forms.TextInput(attrs={"autofocus": True, "autocomplete": "username"}),
    )

    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "That username/email and password combination is not correct.",
    }


class ProfileForm(StyledFormMixin, forms.ModelForm):
    remove_avatar = forms.BooleanField(required=False, label="Remove current avatar")

    class Meta:
        model = UserProfile
        fields = ("bio", "avatar")
        widgets = {
            "bio": forms.Textarea(
                attrs={"rows": 4, "maxlength": 500, "placeholder": "Favourite directors, guilty pleasures..."}
            ),
            "avatar": forms.FileInput(attrs={"accept": "image/jpeg,image/png,image/webp,image/gif"}),
        }
        labels = {"bio": "Bio", "avatar": "Avatar"}
        help_texts = {"avatar": "JPEG, PNG, WebP or GIF, up to 2 MB. Cropped to a square."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._processed_avatar = None

    def clean_bio(self):
        return self.cleaned_data["bio"].strip()

    def clean_avatar(self):
        avatar = self.cleaned_data.get("avatar")
        if isinstance(avatar, UploadedFile):
            self._processed_avatar = process_avatar(avatar)
        return avatar

    def save(self, commit=True):
        profile = super().save(commit=False)
        previous = self.initial.get("avatar")
        previous_name = previous.name if previous else ""
        storage = profile._meta.get_field("avatar").storage

        if self._processed_avatar is not None:
            profile.avatar.save("avatar.webp", self._processed_avatar, save=False)
        elif self.cleaned_data.get("remove_avatar") or self.cleaned_data.get("avatar") is False:
            profile.avatar = ""

        if commit:
            profile.save()
        if previous_name and previous_name != (profile.avatar.name or ""):
            storage.delete(previous_name)
        return profile


class StyledPasswordChangeForm(StyledFormMixin, PasswordChangeForm):
    pass
