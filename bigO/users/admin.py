from bigO.notifications import services as notification_services
from bigO.notifications.providers import NotificationInput
from django.contrib import admin, messages
from django.contrib.auth import admin as auth_admin
from django.contrib.auth import get_user_model
from django.http import HttpResponseRedirect
from django.shortcuts import render

from . import forms

User = get_user_model()


@admin.register(User)
class UserAdmin(auth_admin.UserAdmin):
    actions = ["send_notification"]
    form = forms.UserAdminChangeForm
    add_form = forms.UserAdminCreationForm
    fieldsets = None
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "password1", "password2"),
            },
        ),
    )
    list_display = ["username", "name", "is_superuser"]
    search_fields = ["name", "username"]

    @admin.action()
    def send_notification(self, request, queryset):
        if "apply" in request.POST:  # if user pressed 'apply' on intermediate page
            form = forms.SendNotificationAdminForm(data=request.POST)
            if not form.is_valid():
                self.message_user(request, str(form.errors), level=messages.ERROR)
            else:
                notification_message = {
                    NotificationInput.TITLE: form.cleaned_data["title"],
                    NotificationInput.BODY: form.cleaned_data["body"],
                    NotificationInput.LINK: form.cleaned_data["link"],
                    NotificationInput.ICON_URL: form.cleaned_data["icon_url"],
                    NotificationInput.IMAGE_URL: form.cleaned_data["image_url"],
                }
                for customer in queryset:
                    success, type_or_reason = notification_services.send_notification(
                        to=customer,
                        message=notification_message,
                        type_priorities=[form.cleaned_data["notification_type"]],
                    )
                    message = f"{str(customer)}: {success}-{type_or_reason}"
                    if success:
                        self.message_user(request, message=message, level=messages.SUCCESS)
                    else:
                        self.message_user(request, message=message, level=messages.ERROR)
                return HttpResponseRedirect(request.get_full_path())

        # Create form and pass the data which objects were selected before triggering 'fix_order_delivery' action
        # We create an intermediate page right here
        form = forms.SendNotificationAdminForm(initial={"_selected_action": queryset.values_list("id", flat=True)})

        return render(
            request,
            "utils/admin/intermediate_action.html",
            {"items": queryset, "form": form, "action_name": "send_notification"},
        )
