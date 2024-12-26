import admin_extra_buttons.decorators
import admin_extra_buttons.mixins
import polymorphic.admin

from django import forms
from django.contrib import admin, messages
from django.contrib.admin import widgets
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from . import models, services


class CreateAsymmetricKeyPairForm(forms.Form):
    name = forms.CharField()
    common_name = forms.CharField()
    sign_with = forms.ModelChoiceField(
        required=False,
        queryset=models.PublicKey.objects.all(),
        widget=widgets.AutocompleteSelect(field=models.PublicKey.parent_public_key.field, admin_site=admin.site),
    )
    valid_after = forms.SplitDateTimeField(widget=widgets.AdminSplitDateTime)
    valid_before = forms.SplitDateTimeField(widget=widgets.AdminSplitDateTime)


@admin.register(models.CryptographicObject)
class CryptographicObjectModelAdmin(
    admin_extra_buttons.mixins.ExtraButtonsMixin,
    polymorphic.admin.PolymorphicParentModelAdmin,
):
    child_models = (models.PrivateKey, models.PublicKey)
    list_filter = (polymorphic.admin.PolymorphicChildModelFilter,)

    @admin_extra_buttons.decorators.button(
        decorators=[login_required(login_url="admin:login")],
        permission="core.add_cryptographicobject",
        visible=lambda self: True,
        change_form=False,
        change_list=True,
        # html_attrs={'style': 'background-color:#88FF88;color:black'}
    )
    def create_asymmetric_key_pair(self, request):
        context = self.get_common_context(request, title="Create Asymmetric Key")
        if request.POST:
            form = CreateAsymmetricKeyPairForm(data=request.POST, files=request.FILES)
            if form.is_valid():
                services.create_asymmetric_rsa(
                    name=form.cleaned_data["name"],
                    valid_after=form.cleaned_data["valid_after"],
                    valid_before=form.cleaned_data["valid_before"],
                    parent_public_key_obj=form.cleaned_data.get("sign_with"),
                    common_name=form.cleaned_data["common_name"],
                )
                self.message_user(request, "success", level=messages.SUCCESS)
                if "_addanother" in request.POST:
                    return redirect(request.path)
                return self.response_post_save_add(request=request, obj=None)
        else:
            form = CreateAsymmetricKeyPairForm()

        admin_form = admin.helpers.AdminForm(
            form=form, fieldsets=[(None, {"fields": form.fields})], prepopulated_fields={}, model_admin=self
        )
        media = self.media + admin_form.media
        context["adminform"] = admin_form
        context["media"] = media
        context["show_save_and_continue"] = False
        return render(request, "admin/change_form.html", context=context)


@admin.register(models.PrivateKey)
class PrivateKeyModelAdmin(polymorphic.admin.PolymorphicChildModelAdmin):
    search_fields = ["slug"]


@admin.register(models.PublicKey)
class PublicKeyModelAdmin(polymorphic.admin.PolymorphicChildModelAdmin):
    search_fields = ["slug"]
    autocomplete_fields = ["private_key", "parent_public_key"]
