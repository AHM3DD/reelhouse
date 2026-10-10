"""Small helpers for serving HTMX partials alongside regular page responses."""
from functools import wraps
from urllib.parse import urlencode, urlsplit

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import redirect, resolve_url
from django.template.loader import render_to_string
from django.utils.http import url_has_allowed_host_and_scheme


def is_htmx(request):
    """True for HTMX partial requests (but not history restores, which need full pages)."""
    return (
        request.headers.get("HX-Request") == "true"
        and request.headers.get("HX-History-Restore-Request") != "true"
    )


def htmx_target(request):
    return request.headers.get("HX-Target", "") if is_htmx(request) else ""


def render_partial(request, template_name, context=None, status=200):
    """Render a partial and append pending flash messages as an out-of-band toast swap."""
    html = render_to_string(template_name, context or {}, request=request)
    html += render_to_string("partials/toasts_oob.html", {}, request=request)
    response = HttpResponse(html, status=status)
    response["Vary"] = "HX-Request"
    return response


def safe_next_url(request, fallback=None):
    """Return a same-site redirect target from ?next= / POST next, or the fallback."""
    candidate = request.POST.get("next") or request.GET.get("next")
    if candidate and url_has_allowed_host_and_scheme(
        candidate, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return candidate
    return fallback


def _current_page(request):
    """The page the user is looking at: HX-Current-URL for HTMX, else this request."""
    current = request.headers.get("HX-Current-URL", "")
    if current and url_has_allowed_host_and_scheme(
        current, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        parts = urlsplit(current)
        return parts.path + (f"?{parts.query}" if parts.query else "")
    if request.method == "GET":
        return request.get_full_path()
    return safe_next_url(request, fallback="/")


def login_required_htmx(view_func):
    """Like login_required, but tells HTMX to perform a full-page redirect to the login page."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.user.is_authenticated:
            return view_func(request, *args, **kwargs)
        login_url = f"{resolve_url(settings.LOGIN_URL)}?{urlencode({'next': _current_page(request)})}"
        if is_htmx(request):
            response = HttpResponse(status=204)
            response["HX-Redirect"] = login_url
            return response
        return redirect(login_url)

    return wrapper
