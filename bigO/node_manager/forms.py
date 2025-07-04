import json

import pydantic

from bigO.core import models as core_models
from django import forms
from django.urls import reverse

from . import models, services, typing


class SupervisorRPCConnectTypeForm(forms.Form):
    type = forms.ChoiceField(choices=(("direct", "direct"), ("relay", "relay")))
    method = forms.ChoiceField(choices=(("public_ip", "public ip"), ("easytier", "easytier")))

    def __init__(self, *args, node_obj: models.Node, **kwargs):
        super().__init__(*args, **kwargs)
        self.data._mutable = True
        self.data["type"] = self.data.get("type", "relay")
        self.data["method"] = self.data.get("method", "easytier")
        self.node_obj = node_obj
        current_method = self.data.get("method") or self.fields["method"].initial
        if current_method == "public_ip":
            self.fields["public_ip"] = forms.ModelChoiceField(
                queryset=models.PublicIP.objects.filter(ip_nodepublicips__node=self.node_obj)
            )
            self.data["public_ip"] = self.data.get("public_ip", self.fields["public_ip"].queryset.first().id)
        elif current_method == "easytier":
            related_networls_qs = models.EasyTierNetwork.objects.filter(network_easytiernodes__node=self.node_obj)
            self.fields["easytier_network"] = forms.ModelChoiceField(
                queryset=related_networls_qs, initial=related_networls_qs.first()
            )
            self.data["easytier_network"] = self.data.get(
                "easytier_network", self.fields["easytier_network"].queryset.first().id
            )

    def get_url(self) -> tuple[str, str | None] | None:
        supervisorconfig_obj = getattr(self.node_obj, "supervisorconfig", None)
        xml_rpc_api_expose_port = supervisorconfig_obj.xml_rpc_api_expose_port if supervisorconfig_obj else None
        if xml_rpc_api_expose_port is None:
            self.add_error(None, "xml_rpc_api_expose_port is not active for this node")
            return None
        site_config = core_models.SiteConfiguration.objects.get()
        self.full_clean()
        cleaned_data = getattr(self, "cleaned_data", {})
        method = cleaned_data.get("method", self.fields["method"].initial)
        _type = cleaned_data.get("type", self.fields["type"].initial)
        if not _type or not method:
            return None
        if method not in {"public_ip", "easytier"} or _type not in {"direct", "relay"}:
            return None
        if method == "public_ip":
            ip_obj = self.cleaned_data.get("public_ip", self.fields["public_ip"].initial)
            if not ip_obj:
                return None
            if _type == "direct":
                return (
                    f"https://{ip_obj.ip.ip}:{xml_rpc_api_expose_port}",
                    f"https://{site_config.basic_username}:{site_config.basic_password}@{ip_obj.ip.ip}:{xml_rpc_api_expose_port}",
                )
            elif _type == "relay":
                return (
                    reverse(
                        "node_manager:node_supervisor_server_proxy_root_view",
                        args=[self.node_obj.id, f"{method}:{ip_obj.id}"],
                    ),
                    None,
                )
        elif method == "easytier":
            easytier_network_obj = cleaned_data.get("easytier_network", self.fields["easytier_network"].initial)
            if not easytier_network_obj:
                return None
            if _type == "direct":
                ip = easytier_network_obj.network_easytiernodes.filter(node=self.node_obj).first().ipv4
                return (
                    f"https://{ip.ip}:{xml_rpc_api_expose_port}",
                    f"https://{site_config.basic_username}:{site_config.basic_password}@{ip.ip}:{xml_rpc_api_expose_port}",
                )
            elif _type == "relay":
                return (
                    reverse(
                        "node_manager:node_supervisor_server_proxy_root_view",
                        args=[self.node_obj.id, f"{method}:{easytier_network_obj.id}"],
                    ),
                    None,
                )


class EasyTierNodeModelForm(forms.ModelForm):
    toml_config = forms.CharField(disabled=True, required=False, widget=forms.Textarea)

    class Meta:
        model = models.EasyTierNode
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["toml_config"].initial = self.instance.get_toml_config_content()
        else:
            self.fields["toml_config"].widget = forms.HiddenInput()


class ProgramBinaryModelForm(forms.ModelForm):
    class Meta:
        model = models.ProgramBinary
        exclude = ["hash"]

    def clean(self):
        cleaned_data = super().clean()
        file = cleaned_data.get(models.ProgramBinary.file.field.name)
        if file:
            file_data = file.read()
            file_hash = models.ProgramBinary.get_hash(file_data)
            qs = models.ProgramBinary.objects.filter(hash=file_hash)
            if self.instance and self.instance.pk:
                qs = qs.exclude(id=self.instance.id)
            if qs.exists():
                self.add_error(models.ProgramBinary.file.field.name, f"file already exists, {file_hash}")
            else:
                cleaned_data["file_hash"] = file_hash

        return cleaned_data


class NodeLatestSyncStatModelForm(forms.ModelForm):
    config_to = forms.CharField(widget=forms.Textarea, required=False)

    class Meta:
        model = models.NodeLatestSyncStat
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        config_to_initial = None
        if self.instance and self.instance.id:
            change_node_config_to = services.get_change_node_config_to(self.instance.node)
            if change_node_config_to:
                config_to_initial = change_node_config_to.model_dump_json()
        if config_to_initial:
            self.fields["config_to"].initial = config_to_initial
            self.fields["config_to"].help_text = "waiting for node to confirm it..."

    def clean_config_to(self):
        value = self.cleaned_data.get("config_to")
        if value:
            try:
                dict_value = json.loads(value)
            except json.JSONDecodeError as e:
                raise forms.ValidationError(e)
            try:
                return typing.ConfigSchema(**dict_value)
            except pydantic.ValidationError as e:
                raise forms.ValidationError(e)
        return value

    def save(self, commit=True):
        if "config_to" in self.changed_data and (config_to := self.cleaned_data.get("config_to")):
            services.change_node_config_to(config_to, node=self.instance.node)
        else:
            services.delete_node_config_to(self.instance.node)
        return super().save(commit=commit)
