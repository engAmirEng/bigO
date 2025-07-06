import zoneinfo

from django import forms
from django.contrib.auth import forms as admin_forms
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

User = get_user_model()


class UserAdminChangeForm(admin_forms.UserChangeForm):
    class Meta(admin_forms.UserChangeForm.Meta):
        model = User

    def clean_preferred_timezone(self):
        val = self.cleaned_data.get("preferred_timezone")
        if val:
            if val not in zoneinfo.available_timezones():
                raise forms.ValidationError(
                    _("Invalid timezone: %(value)s"),
                    code="invalid",
                    params={"value": val},
                )
        return val


class UserAdminCreationForm(admin_forms.UserCreationForm):
    """
    Form for User Creation in the Admin Area.
    To change user signup, see UserSignupForm and UserSocialSignupForm.
    """

    class Meta(admin_forms.UserCreationForm.Meta):
        model = User
        error_messages = {
            "username": {"unique": _("This username has already been taken.")},
        }
