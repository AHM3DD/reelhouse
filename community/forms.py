import re

from django import forms

from .models import Comment, WatchlistEntry

COMMENT_MAX_LENGTH = 2000


def normalize_comment(text):
    """Trim, unify newlines, strip control characters and collapse runs of blank lines."""
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", text)
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ("body",)
        labels = {"body": "Your comment"}
        error_messages = {"body": {"required": "Comment cannot be empty."}}
        widgets = {
            "body": forms.Textarea(
                attrs={
                    "rows": 3,
                    "maxlength": COMMENT_MAX_LENGTH,
                    "placeholder": "Share your thoughts. Spoilers? Give people a heads-up.",
                }
            )
        }

    def clean_body(self):
        body = normalize_comment(self.cleaned_data.get("body"))
        if not body:
            raise forms.ValidationError("Comment cannot be empty.")
        if len(body) > COMMENT_MAX_LENGTH:
            raise forms.ValidationError(f"Comments are limited to {COMMENT_MAX_LENGTH} characters.")
        return body


class RatingForm(forms.Form):
    score = forms.IntegerField(
        min_value=1,
        max_value=10,
        error_messages={
            "required": "Choose a rating from 1 to 10.",
            "invalid": "Ratings must be whole numbers from 1 to 10.",
            "min_value": "Ratings must be between 1 and 10.",
            "max_value": "Ratings must be between 1 and 10.",
        },
    )


class FavoriteForm(forms.Form):
    action = forms.ChoiceField(choices=[("add", "Add"), ("remove", "Remove")])


class ListStatusForm(forms.Form):
    status = forms.ChoiceField(choices=[*WatchlistEntry.Status.choices, ("none", "Remove")])
