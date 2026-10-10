"""Fixed-window rate limiting for website endpoints, backed by Django's cache.

DRF endpoints use DRF throttling instead; this covers the server-rendered forms
(login, registration, comment posting).
"""
import time
from functools import wraps

from django.conf import settings
from django.core.cache import cache
from django.shortcuts import render

from .htmx import is_htmx

_PERIODS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def parse_rate(rate):
    """'10/5m' -> (10, 300)."""
    count, period = rate.split("/")
    multiplier = int(period[:-1]) if len(period) > 1 else 1
    return int(count), multiplier * _PERIODS[period[-1]]


def client_ip(request):
    if getattr(settings, "BEHIND_PROXY", False):
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            # The trusted proxy appends the real client address last.
            return forwarded.split(",")[-1].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


def is_rate_limited(request, group, rate, key="ip"):
    limit, window = parse_rate(rate)
    if key == "user" and request.user.is_authenticated:
        ident = f"user:{request.user.pk}"
    else:
        ident = f"ip:{client_ip(request)}"
    bucket = int(time.time() // window)
    cache_key = f"ratelimit:{group}:{ident}:{bucket}"
    cache.add(cache_key, 0, timeout=window + 5)
    try:
        count = cache.incr(cache_key)
    except ValueError:  # expired between add() and incr()
        cache.set(cache_key, 1, timeout=window + 5)
        count = 1
    return count > limit


def rate_limited_response(request):
    if is_htmx(request):
        # Not swapped by HTMX; the global error handler in app.js shows a toast.
        return render(request, "partials/inline_error.html", {"message": "Too many requests."}, status=429)
    return render(request, "429.html", status=429)


def ratelimit(group, rate, key="ip", methods=("POST",)):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if request.method in methods and is_rate_limited(request, group, rate, key=key):
                return rate_limited_response(request)
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator
