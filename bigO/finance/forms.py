from django_jsonform.forms.fields import JSONFormField

from django import forms

from . import models
from .payment_providers import AVAILABLE_PAYMENT_PROVIDERS


class PaymentProviderModelForm(forms.ModelForm):
    class Meta:
        model = models.PaymentProvider
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["provider_key"] = forms.ChoiceField(
            choices=[(i.TYPE_IDENTIFIER, i.TYPE_IDENTIFIER) for i in AVAILABLE_PAYMENT_PROVIDERS]
        )
        self.instance: models.PaymentProvider
        if self.instance and self.instance.id:
            self.fields["provider_key"].disabled = True
            if self.instance.provider_cls.ProviderArgsModel:
                self.fields["provider_args"] = JSONFormField(
                    schema=self.instance.provider_cls.ProviderArgsModel.model_json_schema()
                )
        else:
            if self.data.get("provider_key"):
                provider_cls = [
                    i for i in AVAILABLE_PAYMENT_PROVIDERS if i.TYPE_IDENTIFIER == self.data.get("provider_key")
                ]
                provider_cls = provider_cls[0] if provider_cls else None
                if provider_cls and provider_cls.ProviderArgsModel:
                    self.fields["provider_args"] = JSONFormField(
                        schema=provider_cls.ProviderArgsModel.model_json_schema()
                    )
