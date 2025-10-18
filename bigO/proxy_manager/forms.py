import uuid

import humanize
from django_jsonform.forms.fields import JSONFormField

from django import forms
from django.db.models import Exists
from django.utils.translation import gettext

from . import models
from .subscription import AVAILABLE_SUBSCRIPTION_PLAN_PRICE_PROVIDERS, AVAILABLE_SUBSCRIPTION_PLAN_PROVIDERS


class SubscriptionProfileModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["xray_uuid"].initial = uuid.uuid4()
        self.fields["uuid"].initial = uuid.uuid4()

    class Meta:
        model = models.SubscriptionProfile
        fields = "__all__"


class InternalUserModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["xray_uuid"].initial = uuid.uuid4()

    class Meta:
        model = models.InternalUser
        fields = "__all__"


class SubscriptionPlanModelForm(forms.ModelForm):
    class Meta:
        model = models.SubscriptionPlan
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["plan_provider_key"] = forms.ChoiceField(
            choices=[(i.TYPE_IDENTIFIER, i.TYPE_IDENTIFIER) for i in AVAILABLE_SUBSCRIPTION_PLAN_PROVIDERS]
        )
        self.fields["price_provider_key"] = forms.ChoiceField(
            choices=[(i.TYPE_IDENTIFIER, i.TYPE_IDENTIFIER) for i in AVAILABLE_SUBSCRIPTION_PLAN_PRICE_PROVIDERS]
        )
        self.instance: models.SubscriptionPlan
        if self.instance and self.instance.id:
            self.fields["plan_provider_key"].disabled = True
            if self.instance.plan_provider_cls.ProviderArgsModel:
                self.fields["plan_provider_args"] = JSONFormField(
                    schema=self.instance.plan_provider_cls.ProviderArgsModel.model_json_schema()
                )
            if self.instance.plan_provider_price_cls.ProviderArgsModel:
                self.fields["price_provider_args"] = JSONFormField(
                    schema=self.instance.plan_provider_price_cls.ProviderArgsModel.model_json_schema()
                )
        else:
            if self.data.get("plan_provider_key"):
                plan_provider_cls = [
                    i
                    for i in AVAILABLE_SUBSCRIPTION_PLAN_PROVIDERS
                    if i.TYPE_IDENTIFIER == self.data.get("plan_provider_key")
                ]
                plan_provider_cls = plan_provider_cls[0] if plan_provider_cls else None
                if plan_provider_cls and plan_provider_cls.ProviderArgsModel:
                    self.fields["plan_provider_args"] = JSONFormField(
                        schema=plan_provider_cls.ProviderArgsModel.model_json_schema()
                    )
                plan_provider_price_cls = [
                    i
                    for i in AVAILABLE_SUBSCRIPTION_PLAN_PRICE_PROVIDERS
                    if i.TYPE_IDENTIFIER == self.data.get("price_provider_key")
                ]
                plan_provider_price_cls = plan_provider_cls[0] if plan_provider_cls else None
                if plan_provider_price_cls and plan_provider_price_cls.ProviderArgsModel:
                    self.fields["price_provider_args"] = JSONFormField(
                        schema=plan_provider_price_cls.ProviderArgsModel.model_json_schema()
                    )


class SubscriptionPeriodModelForm(forms.ModelForm):
    class Meta:
        model = models.SubscriptionPeriod
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.id:
            if self.instance.plan.plan_provider_cls.PlanArgsModel:
                self.fields["plan_args"] = JSONFormField(
                    schema=self.instance.plan.plan_provider_cls.PlanArgsModel.model_json_schema()
                )
            for i in [
                models.SubscriptionPeriod.current_download_bytes.field.name,
                models.SubscriptionPeriod.current_upload_bytes.field.name,
                models.SubscriptionPeriod.flow_download_bytes.field.name,
                models.SubscriptionPeriod.flow_upload_bytes.field.name,
            ]:
                current_bytes = getattr(self.instance, i)
                self.fields[i].help_text = gettext("current value is: {0}").format(humanize.naturalsize(current_bytes))
        if self.data.get("plan"):
            plan = models.SubscriptionPlan.objects.filter(id=self.data.get("plan")).first()
            if plan and plan.plan_provider_cls.PlanArgsModel:
                self.fields["plan_args"] = JSONFormField(
                    schema=plan.plan_provider_cls.PlanArgsModel.model_json_schema()
                )


class ConnectionTunnelModelForm(forms.ModelForm):
    class Meta:
        model = models.ConnectionTunnel
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["base_conn_uuid"].initial = uuid.uuid4()


class ConnectionRuleOutboundModelForm(forms.ModelForm):
    class Meta:
        model = models.ConnectionRuleOutbound
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["base_conn_uuid"].initial = uuid.uuid4()


class AgencyUserGroupModelForm(forms.ModelForm):
    class Meta:
        model = models.AgencyUserGroup
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.data.get()
        self.fields["users"].queryset = self.fields["users"].queryset.filter(id=1)

    def clean_users(self):
        users = self.cleaned_data.get("users")
        agency = self.cleaned_data.get("agency")
        if users and agency:
            agencyuser_qs = models.AgencyUser.objects.filter(agency=agency, user_id=OuterRef("id"))
            invalid_users = users.exclude(Exists(agencyuser_qs))
            if invalid_users.exists():
                invalid_users_txt = ", ".join([i.name for i in invalid_users])
                raise forms.ValidationError(f"{invalid_users_txt} are not related to agency ({agency})")
        return users
