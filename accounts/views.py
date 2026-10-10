from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView, PasswordChangeView
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator

from community.services import collection_queryset, favorite_ids_for, profile_stats
from core.htmx import htmx_target, render_partial, safe_next_url
from core.ratelimit import ratelimit

from .forms import LoginForm, ProfileForm, RegistrationForm, StyledPasswordChangeForm
from .models import UserProfile

User = get_user_model()

PROFILE_TABS = [
    ("favorites", "Favorites"),
    ("ratings", "Ratings"),
    ("watchlist", "Watchlist"),
    ("watched", "Watched"),
    ("comments", "Comments"),
]
COLLECTION_TABS = PROFILE_TABS[:4]


@ratelimit("register", "10/h")
def register(request):
    if request.user.is_authenticated:
        return redirect("movies:home")
    next_url = safe_next_url(request)
    if request.method == "POST":
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user, backend="accounts.backends.UsernameOrEmailBackend")
            messages.success(request, f"Welcome to Reelhouse, {user.username}! Start by saving a few favorites.")
            return redirect(next_url or "movies:home")
    else:
        form = RegistrationForm()
    return render(request, "accounts/register.html", {"form": form, "next": next_url or ""})


@method_decorator(ratelimit("login", "10/5m"), name="dispatch")
class SignInView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Welcome back, {form.get_user().username}.")
        return response


class SignOutView(LogoutView):
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        messages.info(request, "You have been logged out.")
        return response


class ChangePasswordView(PasswordChangeView):
    template_name = "accounts/password_change.html"
    form_class = StyledPasswordChangeForm
    success_url = reverse_lazy("accounts:profile_edit")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Your password has been updated.")
        return response


def _tab_context(request, owner, tab, tabs):
    page_size = 10 if tab == "comments" else 24
    paginator = Paginator(collection_queryset(owner, tab), page_size)
    page_obj = paginator.get_page(request.GET.get("page"))
    tmdb_ids = [item.movie.tmdb_id for item in page_obj.object_list]
    return {
        "tab": tab,
        "tabs": tabs,
        "page_obj": page_obj,
        "items": page_obj.object_list,
        "favorite_ids": favorite_ids_for(request.user, tmdb_ids),
    }


def _valid_tab(request, tabs):
    tab = request.GET.get("tab", tabs[0][0])
    return tab if tab in dict(tabs) else tabs[0][0]


def profile_detail(request, username):
    owner = get_object_or_404(User.objects.select_related("profile"), username__iexact=username, is_active=True)
    if owner.username != username:
        return redirect(owner.get_absolute_url(), permanent=True)
    UserProfile.objects.get_or_create(user=owner)

    context = _tab_context(request, owner, _valid_tab(request, PROFILE_TABS), PROFILE_TABS)
    context.update(
        owner=owner,
        is_owner=request.user.is_authenticated and request.user.pk == owner.pk,
        tab_url=reverse("accounts:profile", kwargs={"username": owner.username}),
    )
    if htmx_target(request) == "profile-tab":
        return render_partial(request, "accounts/partials/collection_tab.html", context)
    context["stats"] = profile_stats(owner)
    return render(request, "accounts/profile_detail.html", context)


@login_required
def collection(request):
    context = _tab_context(request, request.user, _valid_tab(request, COLLECTION_TABS), COLLECTION_TABS)
    context.update(owner=request.user, is_owner=True, tab_url=reverse("accounts:collection"))
    if htmx_target(request) == "profile-tab":
        return render_partial(request, "accounts/partials/collection_tab.html", context)
    context["stats"] = profile_stats(request.user)
    return render(request, "accounts/collection.html", context)


@login_required
def profile_edit(request):
    # Always the signed-in user's own profile: there is no URL that targets someone else's.
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    if request.method == "POST":
        form = ProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Your profile has been updated.")
            return redirect("accounts:profile", username=request.user.username)
        messages.error(request, "Please fix the errors below.")
    else:
        form = ProfileForm(instance=profile)
    return render(request, "accounts/profile_edit.html", {"form": form, "profile": profile})
