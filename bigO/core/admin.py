import crypt

import admin_extra_buttons.decorators
import admin_extra_buttons.mixins
from asgiref.sync import async_to_sync
from django_jsonform.forms.fields import JSONFormField
from solo.admin import SingletonModelAdmin

from bigO.net_manager import models as net_manager_models
from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.contrib.admin import widgets
from django.contrib.auth.decorators import login_required
from django.contrib.humanize.templatetags.humanize import naturaltime
from django.db.models import QuerySet
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext

from . import models, tasks
from .dns import AVAILABLE_DNS_PROVIDERS


@admin.register(models.SiteConfiguration)
class SiteConfigurationModelAdmin(SingletonModelAdmin):
    autocomplete_fields = ["nodes_ca_cert"]

    def save_model(self, request, obj, form, change):
        change_htpasswd_content = set(form.changed_data) & {
            models.SiteConfiguration.basic_username.field.name,
            models.SiteConfiguration.basic_password.field.name,
        }
        if change_htpasswd_content and models.SiteConfiguration.htpasswd_content.field.name not in form.changed_data:
            htpasswd_content = f"{obj.basic_username}:{crypt.crypt(obj.basic_password)}"
            obj.htpasswd_content = htpasswd_content
        super().save_model(request, obj, form, change)


class GeneratePrivateKeyForm(forms.Form):
    slug = forms.SlugField()
    key_length = forms.IntegerField(initial=2048)

    def save(self):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=self.cleaned_data["key_length"])
        private_key_content = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
        privatekey_obj = models.PrivateKey()
        privatekey_obj.algorithm = models.PrivateKey.AlgorithmChoices.RSA
        privatekey_obj.content = private_key_content.decode("utf-8")
        privatekey_obj.slug = self.cleaned_data["slug"]
        privatekey_obj.key_length = private_key.key_size
        privatekey_obj.save()
        return privatekey_obj


class SignCertificateForm(forms.Form):
    slug = forms.SlugField()
    is_ca = forms.BooleanField(initial=False, required=False)
    common_name = forms.CharField()
    private_key = forms.ModelChoiceField(
        queryset=models.PrivateKey.objects.all(),
        widget=widgets.AutocompleteSelect(field=models.Certificate.private_key.field, admin_site=admin.site),
    )
    parent_certificate = forms.ModelChoiceField(
        required=False,
        queryset=models.Certificate.objects.all(),
        widget=widgets.AutocompleteSelect(field=models.Certificate.parent_certificate.field, admin_site=admin.site),
    )
    valid_after = forms.SplitDateTimeField(widget=widgets.AdminSplitDateTime)
    valid_before = forms.SplitDateTimeField(widget=widgets.AdminSplitDateTime)

    def save(self):
        from cryptography import x509
        from cryptography.hazmat._oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization

        common_name = self.cleaned_data["common_name"]
        private_key_obj: models.PrivateKey = self.cleaned_data["private_key"]
        valid_after = self.cleaned_data["valid_after"]
        valid_before = self.cleaned_data["valid_before"]
        slug = self.cleaned_data["slug"]
        subject = x509.Name(
            [
                x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
                x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "California"),
                x509.NameAttribute(NameOID.LOCALITY_NAME, "San Francisco"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "My CA Organization"),
                x509.NameAttribute(NameOID.COMMON_NAME, common_name),
            ]
        )
        private_key = serialization.load_pem_private_key(
            private_key_obj.content.encode("utf-8"),
            password=private_key_obj.passphrase.encode("utf-8") if private_key_obj.passphrase else None,
        )
        if not (parent_certificate_obj := self.cleaned_data.get("parent_certificate")):
            certificate = (
                x509.CertificateBuilder()
                .subject_name(subject)
                .issuer_name(subject)
                .public_key(private_key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(valid_after)
                .not_valid_after(valid_before)
                .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
                .add_extension(
                    x509.SubjectAlternativeName([x509.DNSName(common_name)]),
                    critical=False,
                )
                .sign(private_key=private_key, algorithm=hashes.SHA256())
            )
        else:
            csr = (
                x509.CertificateSigningRequestBuilder()
                .subject_name(subject)
                .sign(private_key=private_key, algorithm=hashes.SHA256())
            )
            parent_certificate = x509.load_pem_x509_certificate(parent_certificate_obj.content.encode("utf-8"))
            parent_private_key = serialization.load_pem_private_key(
                parent_certificate_obj.private_key.content.encode("utf-8"),
                password=None,
            )
            certificate = (
                x509.CertificateBuilder()
                .subject_name(csr.subject)
                .issuer_name(parent_certificate.subject)
                .public_key(csr.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(valid_after)
                .not_valid_after(valid_before)
                .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                .add_extension(
                    x509.SubjectAlternativeName([x509.DNSName(common_name)]),
                    critical=False,
                )
                .sign(private_key=parent_private_key, algorithm=hashes.SHA256())
            )
        certificate_content = certificate.public_bytes(serialization.Encoding.PEM)
        certificate_obj = models.Certificate()
        certificate_obj.is_ca = self.cleaned_data["is_ca"]
        certificate_obj.private_key = private_key_obj
        certificate_obj.slug = slug
        certificate_obj.content = certificate_content.decode("utf-8")
        certificate_obj.fingerprint = certificate.fingerprint(hashes.SHA256()).hex()
        certificate_obj.algorithm = models.PrivateKey.AlgorithmChoices.RSA
        certificate_obj.parent_certificate = parent_certificate_obj
        certificate_obj.valid_from = valid_after
        certificate_obj.valid_to = valid_before
        certificate_obj.save()
        return certificate_obj


@admin.register(models.PrivateKey)
class PrivateKeyModelAdmin(admin_extra_buttons.mixins.ExtraButtonsMixin, admin.ModelAdmin):
    search_fields = ["slug"]

    @admin_extra_buttons.decorators.button(
        decorators=[login_required(login_url="admin:login")],
        permission="core.add_privatekey",
        visible=lambda self: True,
        change_form=False,
        change_list=True,
        # html_attrs={'style': 'background-color:#88FF88;color:black'}
    )
    def generate_private_key(self, request):
        context = self.get_common_context(request, title="Generate Private Key")
        if request.POST:
            form = GeneratePrivateKeyForm(data=request.POST)
            if form.is_valid():
                form.save()
                self.message_user(request, "success", level=messages.SUCCESS)
                if "_addanother" in request.POST:
                    return redirect(request.path)
                return self.response_post_save_add(request=request, obj=None)
        else:
            form = GeneratePrivateKeyForm()

        admin_form = admin.helpers.AdminForm(
            form=form, fieldsets=[(None, {"fields": form.fields})], prepopulated_fields={}, model_admin=self
        )
        media = self.media + admin_form.media
        context["adminform"] = admin_form
        context["media"] = media
        context["show_save_and_continue"] = False
        return render(request, "admin/change_form.html", context=context)


@admin.register(models.PublicKey)
class PublicKeyModelAdmin(admin.ModelAdmin):
    search_fields = ["slug"]


class DomainCertificateInline(admin.StackedInline):
    extra = 1
    model = models.DomainCertificate
    autocomplete_fields = ("certificate",)


@admin.register(models.Certificate)
class CertificateModelAdmin(admin_extra_buttons.mixins.ExtraButtonsMixin, admin.ModelAdmin):
    list_display = (
        "__str__",
        "private_key_display",
        "parent_certificate_display",
        "valid_from",
        "valid_to_display",
        "certbot_info",
    )
    search_fields = ["slug", "certbot_info__cert_name"]
    autocomplete_fields = ["private_key", "parent_certificate"]
    inlines = (DomainCertificateInline,)

    @admin.display(ordering="private_key")
    def private_key_display(self, obj):
        if obj.private_key is None:
            return None
        return format_html(
            "<a href='{}'>{}</a>",
            reverse("admin:core_privatekey_change", args=[obj.private_key.id]),
            str(obj.private_key),
        )

    @admin.display(ordering="parent_certificate")
    def parent_certificate_display(self, obj):
        if obj.parent_certificate is None:
            return None
        return format_html(
            "<a href='{}'>{}</a>",
            reverse("admin:core_certificate_change", args=[obj.parent_certificate.id]),
            str(obj.parent_certificate),
        )

    @admin.display(ordering="valid_to")
    def valid_to_display(self, obj):
        return naturaltime(obj.valid_to)

    @admin_extra_buttons.decorators.button(
        decorators=[login_required(login_url="admin:login")],
        permission="core.add_certificate",
        visible=lambda self: True,
        change_form=False,
        change_list=True,
        # html_attrs={'style': 'background-color:#88FF88;color:black'}
    )
    def sign_certificate(self, request):
        context = self.get_common_context(request, title="Sign A Certificate")
        if request.POST:
            form = SignCertificateForm(data=request.POST, files=request.FILES)
            if form.is_valid():
                form.save()
                self.message_user(request, "success", level=messages.SUCCESS)
                if "_addanother" in request.POST:
                    return redirect(request.path)
                return self.response_post_save_add(request=request, obj=None)
        else:
            form = SignCertificateForm()

        admin_form = admin.helpers.AdminForm(
            form=form, fieldsets=[(None, {"fields": form.fields})], prepopulated_fields={}, model_admin=self
        )
        media = self.media + admin_form.media
        context["adminform"] = admin_form
        context["media"] = media
        context["show_save_and_continue"] = False
        return render(request, "admin/change_form.html", context=context)


@admin.register(models.CertbotInfo)
class CertbotInfoModelAdmin(admin.ModelAdmin):
    class CertificateInline(admin.StackedInline):
        extra = 0
        model = models.Certificate

    list_display = ("__str__", "cert_name", "uuid", "valid_to")
    inlines = [CertificateInline]
    actions = ["issue_renew"]

    def get_queryset(self, request):
        return super().get_queryset(request=request).ann_valid_to()

    @admin.display(ordering="valid_to")
    def valid_to(self, obj):
        if obj.valid_to is None:
            return None
        return naturaltime(obj.valid_to)

    @admin.action(description="Issue A Renew")
    def issue_renew(self, request, queryset: QuerySet[models.Domain]):
        count = 0
        for i in queryset:
            certbot_renew_certificates = (
                tasks.certbot_renew_certificates if settings.DEBUG else tasks.certbot_renew_certificates.delay
            )
            certbot_renew_certificates(certbotinfo_id=i.id)
            count += 1
        self.message_user(
            request,
            gettext("issued for {0}").format(count),
            messages.INFO,
        )


class DNSRecordNameInline(admin.StackedInline):
    model = net_manager_models.DNSRecord
    extra = 0
    fk_name = "domain"
    verbose_name = "Name DNS Record"
    show_change_link = True


class DNSRecordValueInline(admin.StackedInline):
    model = net_manager_models.DNSRecord
    extra = 0
    fk_name = "value_domain"
    verbose_name = "Value DNS Record"
    show_change_link = True


@admin.register(models.Domain)
class DomainModelAdmin(admin_extra_buttons.mixins.ExtraButtonsMixin, admin.ModelAdmin):
    list_display = ("__str__", "name", "root", "dns_provider")
    list_filter = ("is_root",)
    search_fields = ("name",)
    actions = ["issue_certificate"]
    autocomplete_fields = ("root",)
    inlines = (DomainCertificateInline, DNSRecordNameInline, DNSRecordValueInline)

    @admin.action(description="Issue A valid Certificate")
    def issue_certificate(self, request, queryset: QuerySet[models.Domain]):
        count = 0
        no_provider_count = 0
        for i in queryset:
            if i.get_dns_provider() is None:
                no_provider_count += 1
                continue
            issue_certificate_for_domain = (
                tasks.issue_certificate_for_domain if settings.DEBUG else tasks.issue_certificate_for_domain.delay
            )
            issue_certificate_for_domain(domain_id=i.id)
            count += 1
        self.message_user(
            request,
            gettext("issued for {0}").format(count),
            messages.INFO,
        )
        self.message_user(
            request,
            gettext("{0} do not have dns provider").format(no_provider_count),
            messages.ERROR,
        )


class DNSProviderModelForm(forms.ModelForm):
    verify = forms.BooleanField(required=False)

    class Meta:
        model = models.DNSProvider
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["provider_key"] = forms.ChoiceField(
            choices=[(i.TYPE_IDENTIFIER, i.TYPE_IDENTIFIER) for i in AVAILABLE_DNS_PROVIDERS]
        )
        if self.instance and self.instance.id:
            self.fields["provider_key"].disabled = True
            self.fields["provider_args"] = JSONFormField(
                schema=self.instance.provider_cls.ProviderArgsModel.model_json_schema()
            )
        else:
            if self.data.get("provider_key"):
                dns_provider_cls = [
                    i for i in AVAILABLE_DNS_PROVIDERS if i.TYPE_IDENTIFIER == self.data.get("provider_key")
                ]
                dns_provider_cls = dns_provider_cls[0] if dns_provider_cls else None
                if dns_provider_cls:
                    self.fields["provider_args"] = JSONFormField(
                        schema=dns_provider_cls.ProviderArgsModel.model_json_schema()
                    )

    def clean(self):
        cleaned_data = super().clean()
        if (
            cleaned_data.get("verify")
            and (provider_key := cleaned_data.get("provider_key"))
            and (provider_args := cleaned_data.get("provider_args"))
        ):
            dns_provider_cls = [i for i in AVAILABLE_DNS_PROVIDERS if i.TYPE_IDENTIFIER == provider_key][0]
            try:
                async_to_sync(dns_provider_cls(args=provider_args).verify)()
            except Exception as e:
                raise forms.ValidationError(e)
        return cleaned_data


@admin.register(models.DNSProvider)
class DNSProviderModelAdmin(admin.ModelAdmin):
    list_display = ("__str__", "name", "provider_key")
    form = DNSProviderModelForm


@admin.register(models.CertificateTask)
class CertificateTaskModelAdmin(admin.ModelAdmin):
    list_display = ("__str__", "certbot_info", "task_type", "is_closed", "is_success", "created_at", "updated_at")

    @admin.display()
    def certbot_info(self, obj):
        certbotinfo = models.CertbotInfo.objects.filter(uuid=obj.certbot_info_uuid).first()
        if certbotinfo is None:
            return obj.certbot_info_uuid
        return format_html(
            "<a href='{}'>{}</a>",
            reverse("admin:core_certbotinfo_change", args=[certbotinfo.pk]),
            obj.certbot_info_uuid,
        )
