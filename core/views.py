from django.shortcuts import render

from .htmx import is_htmx


def csrf_failure(request, reason=""):
    """Friendly CSRF failure page; never echoes the internal reason to the user."""
    if is_htmx(request):
        return render(
            request,
            "partials/inline_error.html",
            {"message": "Your session expired. Please reload the page."},
            status=403,
        )
    return render(request, "403_csrf.html", status=403)
