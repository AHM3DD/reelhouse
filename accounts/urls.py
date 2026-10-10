from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("accounts/register/", views.register, name="register"),
    path("accounts/login/", views.SignInView.as_view(), name="login"),
    path("accounts/logout/", views.SignOutView.as_view(), name="logout"),
    path("accounts/profile/", views.profile_edit, name="profile_edit"),
    path("accounts/password/", views.ChangePasswordView.as_view(), name="password_change"),
    path("collection/", views.collection, name="collection"),
    path("u/<str:username>/", views.profile_detail, name="profile"),
]
