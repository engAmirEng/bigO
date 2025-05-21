from django import forms
from bigO.proxy_manager import models as proxy_manager_models

class NewUserForm(forms.Form):
    title = forms.CharField()
    plan = forms.ModelChoiceField(queryset=proxy_manager_models.SubscriptionPlan.objects.none())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["plan"].queryset =
