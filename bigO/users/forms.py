import zoneinfo

from bigO.notifications.providers import BaseNotificationProvider
from django import forms
from django.contrib.auth import forms as admin_forms
from django.contrib.auth import get_user_model
from django.core.validators import URLValidator
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


class SendNotificationAdminForm(forms.Form):
    _selected_action = forms.CharField(widget=forms.MultipleHiddenInput)

    notification_type = forms.ChoiceField(choices=BaseNotificationProvider.Type.choices)
    title = forms.CharField(max_length=127, required=False)
    body = forms.CharField(widget=forms.Textarea, max_length=511)
    link = forms.URLField(validators=[URLValidator(schemes=["https"])], required=False)
    icon_url = forms.URLField(validators=[URLValidator(schemes=["https"])], required=False)
    image_url = forms.URLField(validators=[URLValidator(schemes=["https"])], required=False)

    def clean_title(self, *args, **kwargs):
        value = self.cleaned_data.get("title")
        if value == "":
            return None
        return value

    def clean_link(self, *args, **kwargs):
        value = self.cleaned_data.get("link")
        if value == "":
            return None
        return value

    class Media:
        css = {"all": ("/static/admin/css/widgets.css",)}
        js = [
            "/admin/jsi18n/",
            "/static/admin/js/core.js",
        ]
