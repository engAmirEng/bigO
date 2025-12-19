from django.contrib import admin

from . import models


@admin.register(models.AccountProvider)
class AccountProviderModelAdmin(admin.ModelAdmin):
    pass


@admin.register(models.TelegramApp)
class TelegramAppModelAdmin(admin.ModelAdmin):
    pass


@admin.register(models.TelegramAccount)
class TelegramAccountModelAdmin(admin.ModelAdmin):
    pass


@admin.register(models.TelegramSession)
class TelegramSessionModelAdmin(admin.ModelAdmin):
    pass
