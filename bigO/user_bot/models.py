import netfields
import phonenumber_field.modelfields

from bigO.utils.models import TimeStampedModel
from django.db import models


class AccountProvider(TimeStampedModel, models.Model):
    name = models.SlugField(unique=True)
    telegram_bot = models.ForeignKey("telegram_bot.TelegramBot", on_delete=models.PROTECT, related_name="+")


class TelegramApp(TimeStampedModel, models.Model):
    api_id = models.IntegerField()
    api_hash = models.CharField(max_length=255)


class TelegramAccount(TimeStampedModel, models.Model):
    account_provider = models.ForeignKey(AccountProvider, on_delete=models.PROTECT, related_name="+")
    username = models.CharField(max_length=127, unique=True)
    password = models.CharField(max_length=255)
    phonenumber = phonenumber_field.modelfields.PhoneNumberField(unique=True)
    owners = models.ManyToManyField("users.User", blank=True)


class TelegramSession(TimeStampedModel, models.Model):
    account = models.ForeignKey(TelegramAccount, on_delete=models.CASCADE, related_name="+")
    app = models.ForeignKey(TelegramApp, on_delete=models.CASCADE, related_name="+")
    sqlite_file = models.FileField(upload_to="protected/user_bot/telegram_sqlite_sessions/", null=True, blank=True)
    logged_in = models.DateTimeField(null=True, blank=True)
    last_activity_at = models.DateTimeField(null=True, blank=True)
    last_used_ip = netfields.InetAddressField(null=True, blank=True)
