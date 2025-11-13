import asyncio

from asgiref.sync import async_to_sync

import aiogram
from django.contrib import admin, messages

from . import models


@admin.register(models.TelegramBot)
class TelegramBotModelAdmin(admin.ModelAdmin):
    actions = ("set_webhook_action", "delete_webhook_action", "get_webhook_info_action")
    search_fields = ("tid", "tusername", "title")
    list_display = ("id", "title", "tid", "tusername", "is_revoked", "is_powered_off")

    @async_to_sync
    async def set_webhook_action(what, self, request, queryset):
        async def set_webhook(telegram_bot_obj: models.TelegramBot):
            try:
                await telegram_bot_obj.sync_webhook()
                success = True
            except AssertionError:
                success = False
            self.message_user(
                request,
                f"{str(telegram_bot_obj)} {'succeeded' if success else 'failed'}",
                level=messages.SUCCESS if success else messages.ERROR,
            )

        tasks = [set_webhook(bot) async for bot in queryset]
        await asyncio.gather(*tasks)

    @async_to_sync
    async def delete_webhook_action(what, self, request, queryset):
        async def delete_webhook(telegram_bot_obj):
            bot = telegram_bot_obj.get_aiobot()
            success = await bot.delete_webhook()
            self.message_user(
                request,
                f"{str(telegram_bot_obj)} {'succeeded' if success else 'failed'}",
                level=messages.SUCCESS if success else messages.ERROR,
            )

        tasks = [delete_webhook(bot) async for bot in queryset]
        await asyncio.gather(*tasks)

    @async_to_sync
    async def get_webhook_info_action(what, self, request, queryset):
        async def get_webhook_info(telegram_bot_obj):
            bot = telegram_bot_obj.get_aiobot()
            info: aiogram.types.WebhookInfo = await bot.get_webhook_info()

            m = str(telegram_bot_obj) + " "
            if not info.url:
                message = m + f"webhook url is not set, should be {telegram_bot_obj.webhook_url}"
                level = messages.INFO
            elif telegram_bot_obj.webhook_url == info.url:
                message = m + f"webhook url correctly set to {info.url}"
                level = messages.SUCCESS
            else:
                message = m + f"webhook url is {info.url}, should be {telegram_bot_obj.webhook_url}"
                level = messages.ERROR
            self.message_user(request, message, level=level)

        tasks = [get_webhook_info(bot) async for bot in queryset]
        await asyncio.gather(*tasks)


@admin.register(models.TelegramUser)
class TelegramUserModelAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "bot",
        "name_display",
        "tlanguage_code",
        "tis_premium",
        "tadded_to_attachment_menu",
        "created_at",
        "last_accessed_at",
    )
    search_fields = ("user__name", "user__username", "tfirst_name", "tlast_name", "tusername")
    autocomplete_fields = ("user", "bot")

    @admin.display()
    def name_display(self, obj: models.TelegramUser):
        return f"{obj.tfirst_name} {obj.tlast_name} @{obj.tusername}"


@admin.register(models.TelegramFile)
class TelegramFileAdmin(admin.ModelAdmin):
    list_display = ["id", "file_id", "file_unique_id"]
