from django_jsonform.forms.fields import JSONFormField

import django.contrib.admin.widgets
from django import forms

from . import models, providers


class AdminFilteredSelect(django.contrib.admin.widgets.FilteredSelectMultiple):
    """
    It does the trick
    """

    def value_from_datadict(self, data, files, name):
        return data.get(name)


class NotificationAccountModelForm(forms.ModelForm):
    class Meta:
        model = models.NotificationAccount
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["provider"] = forms.ChoiceField(choices=[(i.KEY, i.TITLE) for i in providers.AVAILABLE_PROVIDERS])
        if self.instance and self.instance.id:
            provider_cls = self.instance.get_provider_class()
            if provider_cls.EXTRAS_INPUT_SCHEMA:
                self.fields["extras"] = JSONFormField(schema=provider_cls.EXTRAS_INPUT_SCHEMA)
        if self.data.get("provider"):
            provider_cls_list = [i for i in providers.AVAILABLE_PROVIDERS if i.KEY == self.data.get("provider")]
            if provider_cls_list:
                provider_cls = provider_cls_list[0]
                if provider_cls.EXTRAS_INPUT_SCHEMA:
                    self.fields["extras"] = JSONFormField(schema=provider_cls.EXTRAS_INPUT_SCHEMA)


class ForeignTemplateForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["const_message_key"].widget = AdminFilteredSelect(
            verbose_name=models.MessageContext._meta.get_field("key").verbose_name,
            is_stacked=False,
            choices=models.ConstMessageContext.choices(),
        )

    class Meta:
        model = models.ForeignTemplate
        fields = "__all__"


class MessageContextForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["key"].widget = AdminFilteredSelect(
            verbose_name=models.MessageContext._meta.get_field("key").verbose_name,
            is_stacked=False,
            choices=models.ConstMessageContext.choices(),
        )

    class Meta:
        model = models.MessageContext
        fields = "__all__"
