from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class UsernameOrEmailBackend(ModelBackend):
    """Authenticate with either username or email (both case-insensitive)."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
        if not username or password is None:
            return None
        username = username.strip()
        lookup = {"email__iexact": username} if "@" in username else {"username__iexact": username}
        try:
            user = UserModel._default_manager.get(**lookup)
        except UserModel.DoesNotExist:
            # Run the hasher anyway so response time does not reveal whether the account exists.
            UserModel().set_password(password)
            return None
        except UserModel.MultipleObjectsReturned:
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
