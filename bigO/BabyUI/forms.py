from bigO.proxy_manager import models as proxy_manager_models
from bigO.proxy_manager import services as proxy_manager_services
from bigO.proxy_manager.subscription import planproviders
from django import forms


class NewUserForm(forms.Form):
    title = forms.CharField()
    description = forms.CharField(required=False)
    plan = forms.ModelChoiceField(queryset=proxy_manager_models.SubscriptionPlan.objects.none())
    expiry_days = forms.IntegerField(required=False)
    volume_gb = forms.IntegerField(required=False)

    def __init__(self, *args, agency, **kwargs):
        super().__init__(*args, **kwargs)
        subscriptionplan_qs = proxy_manager_services.get_agent_available_plans(agency=agency)
        self.fields["plan"].queryset = subscriptionplan_qs

    def get_plan_args(self) -> dict:
        plan = self.cleaned_data["plan"]
        if plan.plan_provider_cls == planproviders.TypeSimpleDynamic1:
            expiry_days = self.cleaned_data["expiry_days"]
            volume_gb = self.cleaned_data["volume_gb"]
            return {"total_usage_limit_bytes": volume_gb * 1000_000_000, "expiry_seconds": expiry_days * 24 * 60 * 60}
        elif plan.plan_provider_cls == planproviders.TypeSimpleStrict1:
            return {}

    def clean_volume_gb(self):
        plan = self.cleaned_data.get("plan")
        value = self.cleaned_data.get("volume_gb")
        if plan and plan.plan_provider_cls == planproviders.TypeSimpleDynamic1:
            if not value:
                raise forms.ValidationError("this is required")
        return value

    def clean_expiry_days(self):
        plan = self.cleaned_data.get("plan")
        value = self.cleaned_data.get("expiry_days")
        if plan and plan.plan_provider_cls == planproviders.TypeSimpleDynamic1:
            if not value:
                raise forms.ValidationError("this is required")
        return value


class RenewUserForm(forms.Form):
    plan = forms.ModelChoiceField(queryset=proxy_manager_models.SubscriptionPlan.objects.none())
    expiry_days = forms.IntegerField(required=False)
    volume_gb = forms.IntegerField(required=False)

    def __init__(
        self,
        *args,
        profile: proxy_manager_models.SubscriptionProfile,
        current_period: proxy_manager_models.SubscriptionPeriod | None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        subscriptionplan_qs = proxy_manager_services.get_agent_available_plans(
            agency=profile.initial_agency, current_period=current_period
        )
        self.fields["plan"].queryset = subscriptionplan_qs

    def get_plan_args(self) -> dict:
        plan = self.cleaned_data["plan"]
        if plan.plan_provider_cls == planproviders.TypeSimpleDynamic1:
            expiry_days = self.cleaned_data["expiry_days"]
            volume_gb = self.cleaned_data["volume_gb"]
            return {"total_usage_limit_bytes": volume_gb * 1000_000_000, "expiry_seconds": expiry_days * 24 * 60 * 60}
        elif plan.plan_provider_cls == planproviders.TypeSimpleStrict1:
            return {}

    def clean_volume_gb(self):
        plan = self.cleaned_data.get("plan")
        value = self.cleaned_data.get("volume_gb")
        if plan and plan.plan_provider_cls == planproviders.TypeSimpleDynamic1:
            if not value:
                raise forms.ValidationError("this is required")
        return value

    def clean_expiry_days(self):
        plan = self.cleaned_data.get("plan")
        value = self.cleaned_data.get("expiry_days")
        if plan and plan.plan_provider_cls == planproviders.TypeSimpleDynamic1:
            if not value:
                raise forms.ValidationError("this is required")
        return value
