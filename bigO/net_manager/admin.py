from asgiref.sync import async_to_sync
from django import forms
from django.utils import timezone

from . import models
from django.contrib import admin
from bigO.core import models as core_models
from bigO.node_manager import models as node_manager_models



class DNSRecordModelForm(forms.ModelForm):
    verify = forms.BooleanField(required=False)

    class Meta:
        model = models.DNSRecord
        fields = "__all__"


    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("verify"):
            domain: core_models.Domain = cleaned_data["domain"]
            dns_provider_obj: core_models.DNSProvider | None = domain.get_dns_provider()
            if dns_provider_obj is None:
                raise forms.ValidationError("domain does not have dns provider")
            root_domain: core_models.Domain | None = domain.get_root()
            if root_domain is None:
                raise forms.ValidationError("selected domain does not have root")
            dns_provider = dns_provider_obj.get_provider()
            value_domain: core_models.Domain | None = cleaned_data.get("value_domain")
            value_ip: node_manager_models.PublicIP | None = cleaned_data.get("value_ip")
            if value_ip is None and value_domain is None:
                raise forms.ValidationError("no value_domain or value_ip supplied")
            value = value_domain.name if value_domain else str(value_ip.ip.ip)
            record_type = cleaned_data["type"]
            proxied = cleaned_data["proxied"]
            if self.instance and self.instance.pk and cleaned_data.get("id_provider"):
                id_provider = cleaned_data.get("id_provider")
            else:
                id_provider = async_to_sync(dns_provider.get_record_id)(base_domain_name=root_domain.name, name=domain.name)
            if id_provider:
                async_to_sync(dns_provider.update_record)(
                    record_id=id_provider,
                    base_domain_name=root_domain.name,
                    name=domain.name,
                    content=value,
                    type=models.DNSRecord.TypeChoices(record_type).to_record_type(),
                    proxied=proxied,
                    comment="dns record")
            else:
                id_provider = async_to_sync(dns_provider.create_record)(
                    base_domain_name=root_domain.name,
                    name=domain.name,
                    content=value,
                    type=models.DNSRecord.TypeChoices(record_type).to_record_type(),
                    proxied=proxied,
                    comment="dns record")

            if not id_provider:
                raise forms.ValidationError(f"no id returned form {str(dns_provider)}")
            cleaned_data["provider_sync_at"] = timezone.now()
            cleaned_data["id_provider"] = id_provider
        return cleaned_data

    def save(self, commit=True):
        if self.cleaned_data.get("verify"):
            self.instance.id_provider = self.cleaned_data.get("id_provider")
            self.instance.provider_sync_at = self.cleaned_data.get("provider_sync_at")
        return super().save(commit=commit)




@admin.register(models.DNSRecord)
class DNSRecordModelAdmin(admin.ModelAdmin):
    list_display = ("id", "domain", "type", "proxied", "value_ip", "value_domain")
    search_fields = ("domain__name", "value_ip__ip", "value_domain__name")
    form = DNSRecordModelForm
    autocomplete_fields = ("domain", "value_ip", "value_domain")

    def delete_queryset(self, request, queryset):
        # TODO delete from provider?!
        return super().delete_queryset(request=request, queryset=queryset)

    def delete_model(self, request, obj: models.DNSRecord):
        if obj.id_provider and (dns_provider_obj := obj.domain.get_dns_provider()) and (root_domain := obj.domain.get_root()):
            dns_provider = dns_provider_obj.get_provider()
            async_to_sync(dns_provider.delete_record)(base_domain_name=root_domain.name, record_id=obj.id_provider)
        return super().delete_model(request=request, obj=obj)
