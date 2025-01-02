import admin_extra_buttons.decorators
import admin_extra_buttons.mixins
from solo.admin import SingletonModelAdmin

from django import forms
from django.contrib import admin, messages
from django.contrib.admin import widgets
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from . import models


@admin.register(models.SiteConfiguration)
class SiteConfigurationModelAdmin(SingletonModelAdmin):
    autocomplete_fields = ["nodes_ca_cert"]


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


@admin.register(models.Certificate)
class CertificateModelAdmin(admin_extra_buttons.mixins.ExtraButtonsMixin, admin.ModelAdmin):
    search_fields = ["slug"]
    autocomplete_fields = ["private_key", "parent_certificate"]

    @admin_extra_buttons.decorators.button(
        decorators=[login_required(login_url="admin:login")],
        permission="core.add_cryptographicobject",
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
