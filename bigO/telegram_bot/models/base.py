from __future__ import annotations

import random
import string
from enum import Enum
from typing import Literal

from asgiref.sync import sync_to_async
from wonderwords import RandomWord

import aiogram
import aiogram.exceptions
import aiogram.utils.token
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.session.base import BaseSession
from aiogram.enums import ChatMemberStatus, ParseMode
from bigO.users.models import User
from bigO.utils.models import TimeStampedModel
from django.db import models
from django.db.models import CheckConstraint, Q, UniqueConstraint
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from .. import settings
from .telegram_mappings import TelegramChat


class TelegramBotManager(models.Manager):
    async def register(
        self, token: str, tid: int, tbot_name: str, tusername: str, added_from: TelegramBot, added_by: User
    ):
        session = AiohttpSession(proxy=settings.TELEGRAM_PROXY)
        aiobot = aiogram.Bot(token, session=session)
        obj: TelegramBot = self.model()
        obj.tid = tid
        obj.title = tbot_name
        obj.tusername = tusername
        obj.api_token = aiobot.token
        obj.secret_token = self.model.generate_secret_token()
        obj.url_specifier = self.model.generate_url_specifier()
        obj.domain_name = (
            self.model.generate_sub_domain_name() + "." + random.choice(settings.TELEGRAM_WEBHOOK_FLYING_DOMAINS)
        )
        obj.is_master = False
        obj.added_by = added_by
        obj.added_from = added_from

        await obj.asave()
        return obj


class TelegramBot(TimeStampedModel, models.Model):
    tid = models.BigIntegerField()
    tusername = models.CharField(max_length=254)
    title = models.CharField(max_length=63)
    api_token = models.CharField(max_length=127)
    secret_token = models.CharField(max_length=255)
    webhook_url_specifier = models.CharField(max_length=255, db_index=True, null=True, blank=True)
    webhook_domain = models.ForeignKey(
        "core.Domain", on_delete=models.PROTECT, related_name="+", null=True, blank=True
    )
    webhook_synced_at = models.DateTimeField(null=True, blank=True)
    is_revoked = models.BooleanField(default=False)
    is_powered_off = models.BooleanField(default=False)

    objects = TelegramBotManager()

    def __str__(self):
        return f"{self.id}-{self.title}({self.tusername})"

    @property
    def webhook_url(self):
        if self.webhook_domain is None or not self.webhook_url_specifier:
            return None
        path = reverse("telegram_bot:webhook", kwargs={"url_specifier": self.webhook_url_specifier})
        return f"{self.webhook_domain.name}{path}"

    @property
    def is_active(self):
        return self.webhook_synced_at and not self.is_revoked and not self.is_powered_off

    class ChangePowerResult(str, Enum):
        ALREADY_THERE = "already_there"
        DONE = "done"

    async def change_power(self, status: bool):
        if self.is_powered_off == (not status):
            return self.ChangePowerResult.ALREADY_THERE
        self.is_powered_off = not status
        await self.asave()
        return self.ChangePowerResult.DONE

    def get_aiobot(self, session: BaseSession | None = None) -> aiogram.Bot:
        return self.new_aiobot(self.api_token, session=session)

    class RegisterResult(str, Enum):
        DONE = "done"
        TOKEN_NOT_A_TOKEN = "token_not_a_token"
        REVOKED_TOKEN = "revoked_token"
        REVOKE_REQUIRED = "revoke_required"
        ALREADY_ADDED = "added_already"

    @classmethod
    async def do_register(
        cls, token: str, added_from_bot_obj: TelegramBot, added_by_user_obj: User
    ) -> (TelegramBot | None, RegisterResult):
        try:
            aiogram.utils.token.validate_token(token)
        except aiogram.utils.token.TokenValidationError:
            return None, cls.RegisterResult.TOKEN_NOT_A_TOKEN

        new_aiobot = cls.new_aiobot(token)
        try:
            new_aiobot_user = await new_aiobot.get_me()
        except aiogram.exceptions.TelegramUnauthorizedError:
            return None, cls.RegisterResult.REVOKED_TOKEN
        is_revoke_token_required, revoked_count = await cls.handle_perv_same_bots(
            added_by_user_obj=added_by_user_obj, tid=new_aiobot_user.id, api_token=token
        )
        if is_revoke_token_required:
            return None, cls.RegisterResult.REVOKE_REQUIRED
        user_same_bots_qs = cls.objects.filter(added_by=added_by_user_obj, tid=new_aiobot_user.id)
        if already_added_bot_obj := await user_same_bots_qs.afirst():
            return already_added_bot_obj, cls.RegisterResult.ALREADY_ADDED
        bot_name = await new_aiobot.get_my_name()
        new_bot_obj = await cls.objects.register(
            token=token,
            tid=new_aiobot_user.id,
            tbot_name=bot_name.name,
            tusername=new_aiobot_user.username,
            added_from=added_from_bot_obj,
            added_by=added_by_user_obj,
        )
        await new_bot_obj.sync_webhook()
        return new_bot_obj, cls.RegisterResult.DONE

    async def sync_webhook(self):
        webhook_url = await sync_to_async(lambda: self.webhook_url)()
        assert webhook_url
        aiobot = self.get_aiobot()
        success = await aiobot.set_webhook(webhook_url, secret_token=self.secret_token)
        self.webhook_synced_at = timezone.now()
        await self.asave()
        assert success

    @classmethod
    async def handle_perv_same_bots(cls, added_by_user_obj: User, tid: int, api_token: str) -> (bool, int):
        """
        call this after you fully asserted that the api_token is valid
        returns: tuple[is_revoke_token_required, revoked_count]
        """

        same_active_bots_qs = cls.objects.filter(tid=tid, is_revoked=False).exclude(added_by=added_by_user_obj)
        if await same_active_bots_qs.aexists():
            if await same_active_bots_qs.filter(api_token=api_token).aexists():
                return True, 0
            count = await same_active_bots_qs.acount()
            if count > 50:
                raise Exception("cannot revoke more than 50 bots")
            async for i in same_active_bots_qs:
                await i.revoke(notify_the_owner=True)
            return False, count
        return False, 0

    async def revoke(self, notify_the_owner: bool):
        self.is_revoked = True
        await self.asave()
        if notify_the_owner:
            tasks.send_message.delay(tid=self.added_by_id, message=str(_("ربات شما معلق شد")))

    @staticmethod
    def generate_secret_token():
        length = random.randint(50, 255)
        allowed_characters = string.ascii_letters + string.digits + "-" + "_"
        secret_token = "".join(random.choice(allowed_characters) for _ in range(length))
        return secret_token

    @staticmethod
    def generate_url_specifier():
        r = RandomWord()
        slash_parts_count = random.randint(1, 4)
        slash_parts = []
        for i in range(slash_parts_count):
            part_count = random.randint(1, 4)
            part = "-".join(r.random_words(amount=part_count, word_max_length=10))
            slash_parts.append(part)
        return "/".join(slash_parts)

    @staticmethod
    def generate_sub_domain_name():
        # TODO
        return "tel"

        r = RandomWord()
        part_count = random.randint(1, 4)
        sub_domain_name = "-".join(r.random_words(amount=part_count, word_max_length=10))
        return sub_domain_name

    @staticmethod
    def new_aiobot(token: str, session: BaseSession | None = None) -> aiogram.Bot:
        from ..settings import TELEGRAM_SESSION

        session = session or TELEGRAM_SESSION
        return aiogram.Bot(token, default=DefaultBotProperties(parse_mode=ParseMode.HTML), session=session)


class TelegramUser(TimeStampedModel, models.Model):
    user = models.ForeignKey(
        User, related_name="telegramuserprofiles", on_delete=models.CASCADE, null=True, blank=True
    )
    tid = models.BigIntegerField(db_comment="user id in telegram")
    bot = models.ForeignKey(TelegramBot, related_name="telegramuserprofiles", on_delete=models.CASCADE)
    last_accessed_at = models.DateTimeField()
    tfirst_name = models.CharField(max_length=255)
    tlast_name = models.CharField(max_length=255, null=True, blank=True)
    tusername = models.CharField(max_length=255, null=True, blank=True)
    tlanguage_code = models.CharField(max_length=3, null=True, blank=True)
    tis_premium = models.BooleanField(null=True, blank=True)
    tadded_to_attachment_menu = models.BooleanField(null=True, blank=True)

    class Meta:
        constraints = [UniqueConstraint(fields=("tid", "bot"), name="unique_tuser_tbot")]

    def __str__(self):
        res = f"{self.id}-{self.bot.title}"
        if self.user:
            res += f"({self.user.username})"
        else:
            res += f"(__{self.tfirst_name})"
        return res

    @classmethod
    async def from_update(cls, *, bot_obj: TelegramBot, tuser: aiogram.types.User):
        now = timezone.now()
        try:
            tuser_obj = (
                await TelegramUser.objects.filter(tid=tuser.id, bot_id=bot_obj.id).select_related("bot", "user").aget()
            )
            tuser_obj.last_accessed_at = now
            await tuser_obj.asave()
            return False, tuser_obj
        except TelegramUser.DoesNotExist:
            tuser_obj = cls(user=None)
            tuser_obj.bot = bot_obj
            tuser_obj.tid = tuser.id
            tuser_obj.last_accessed_at = now
            tuser_obj.tfirst_name = tuser.first_name
            tuser_obj.tlast_name = tuser.last_name
            tuser_obj.tusername = tuser.username
            tuser_obj.tlanguage_code = tuser.language_code
            tuser_obj.tis_premium = tuser.is_premium
            tuser_obj.tadded_to_attachment_menu = tuser.added_to_attachment_menu
            await tuser_obj.asave()
            return True, tuser_obj


class TelegramChatMemberManager(models.Manager):
    async def from_aio_sync(
        self,
        tchatmember: (
            aiogram.types.ChatMemberOwner
            | aiogram.types.ChatMemberAdministrator
            | aiogram.types.ChatMemberMember
            | aiogram.types.ChatMemberRestricted
            | aiogram.types.ChatMemberLeft
            | aiogram.types.ChatMemberBanned
        ),
        tchat_obj: TelegramChat,
        tbot_or_user_obj: TelegramUser | TelegramBot,
    ) -> tuple[Literal["created", "updated", "not_changed"], TelegramChatMember]:
        if isinstance(tbot_or_user_obj, TelegramUser):
            tuser_obj = tbot_or_user_obj
            tbot_obj = None
            obj = await self.filter(tchat=tchat_obj, tuser=tuser_obj).afirst()
        elif isinstance(tbot_or_user_obj, TelegramBot):
            tuser_obj = None
            tbot_obj = tbot_or_user_obj
            obj = await self.filter(tchat=tchat_obj, tbot=tbot_obj).afirst()
        else:
            raise NotImplementedError(f"{type(tbot_or_user_obj)=} which is not expected.")
        if obj is not None:
            if obj.status != tchatmember.status:
                status = "updated"
            else:
                status = "not_changed"
        else:
            obj = self.model()
            obj.tchat = tchat_obj
            obj.tuser = tuser_obj
            obj.tbot = tbot_obj
            obj.status = tchatmember.status
            await obj.asave()
            status = "created"

        return status, obj


class TelegramChatMember(TimeStampedModel, models.Model):
    """
    Defines the status of a user/bot in a chat
    """

    class Status(models.TextChoices):
        CREATOR = ChatMemberStatus.CREATOR
        ADMINISTRATOR = ChatMemberStatus.ADMINISTRATOR
        MEMBER = ChatMemberStatus.MEMBER
        RESTRICTED = ChatMemberStatus.RESTRICTED
        LEFT = ChatMemberStatus.LEFT
        KICKED = ChatMemberStatus.KICKED

    tchat = models.ForeignKey("TelegramChat", on_delete=models.CASCADE, related_name="+")

    tbot = models.ForeignKey("TelegramBot", on_delete=models.CASCADE, related_name="+", null=True, blank=True)
    tuser = models.ForeignKey("TelegramUser", on_delete=models.CASCADE, related_name="+", null=True, blank=True)

    status = models.CharField(max_length=31, choices=Status.choices)

    objects = TelegramChatMemberManager()

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=("tbot", "tchat"), condition=Q(tbot__isnull=False), name="unique_tbot_chat_condition"
            ),
            UniqueConstraint(
                fields=("tuser", "tchat"), condition=Q(tuser__isnull=False), name="unique_tuser_chat_condition"
            ),
            CheckConstraint(
                check=Q(Q(tbot__isnull=True, tuser__isnull=False) | Q(tbot__isnull=False, tuser__isnull=True)),
                name="one_of_tbot_or_tuser",
            ),
        ]

    @classmethod
    async def handle_aio_get_chat_exception(
        cls, exception: aiogram.exceptions.TelegramForbiddenError, chat_tid: int, tbot_obj: TelegramBot
    ) -> tuple[None, tuple[None, Status]] | tuple[TelegramChatMember, tuple[Status, Status]]:
        perv_status = None
        if exception.message == "Forbidden: bot was kicked from the channel chat":
            status = cls.Status.KICKED
        else:
            raise NotImplementedError(f"TelegramForbiddenError with {exception.message=}")
        try:
            obj = await cls.objects.aget(tbot=tbot_obj, tchat__tid=chat_tid)
        except cls.DoesNotExist:
            obj = None
            if status in (cls.Status.KICKED, cls.Status.LEFT, cls.Status.RESTRICTED):
                happening_logger.critical(f"{chat_tid=} is at {status=} for {str(tbot_obj)} but is not present in db.")
        if obj:
            perv_status = obj.status
            obj.status = status
            await obj.asave()
        return obj, (perv_status, status)
