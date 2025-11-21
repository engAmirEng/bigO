import logging
from enum import Enum
from typing import Optional, Union

from asgiref.sync import sync_to_async

import aiogram.exceptions
from aiogram import Bot
from aiogram.filters import CommandStart, Filter
from aiogram.types import CallbackQuery, Message
from aiogram.utils.deep_linking import create_deep_link
from bigO.telegram_bot import models as telegram_bot_models
from bigO.telegram_bot.models import TelegramUser
from django.http import QueryDict


class MasterBotFilter(Filter):
    async def __call__(self, *args, bot_obj: telegram_bot_models.TelegramBot, **kwargs) -> bool:
        return bot_obj.is_master


class OwnerBotFilter(Filter):
    async def __call__(
        self,
        update: Union[Message, CallbackQuery],
        user: TelegramUser,
        bot_obj: telegram_bot_models.TelegramBot,
        **kwargs,
    ) -> bool:
        if user.is_anonymous:
            return False
        assert update.from_user.id == user.tid
        added_by = await sync_to_async(bot_obj.added_by.get_real_instance)()
        if isinstance(added_by, TelegramUser):
            return added_by.tid == update.from_user.id
        if not bot_obj.is_master:
            logging.info(f"owner of {str(bot_obj)} is not of type TelegramUser")
        return False


MASTER_PATH_FILTERS = (MasterBotFilter(),)
SUB_OWNER_PATH_FILTERS = (~MasterBotFilter(), OwnerBotFilter())


class QueryPathName(str, Enum):
    """
    Path names that are used in start deep link command
    """

    ASSOCIATE_TO_USER = "atu"
    ASSOCIATE_TO_ACCOUNT = "ata"
    MEMBER_PROFILE_DETAIL = "mpd"


def query_magic_dispatcher(pathname: QueryPathName) -> aiogram.MagicFilter:
    """
    Pass the return value to StartCommandQueryFilter.query_magic to  Dispatches deep link start commands
    """
    return aiogram.F.get("a") == pathname.value


def get_dispatch_query(bot_username: str, pathname: QueryPathName, **kwargs) -> str:
    """
    returns start command deep link that can be dispatched with pathname
    """
    qd = QueryDict(mutable=True)
    qd.update({"a": pathname.value, **kwargs})
    res = qd.urlencode()
    return create_deep_link(username=bot_username, link_type="start", payload=res, encode=True)


class StartCommandQueryFilter(CommandStart):
    def __init__(self, command_magic: Optional[aiogram.MagicFilter] = None, query_magic: [aiogram.MagicFilter] = None):
        super().__init__(deep_link=True, deep_link_encoded=True, magic=command_magic)
        self.query_magic = query_magic

    async def __call__(self, message: Message, bot: Bot):
        result = await super().__call__(message=message, bot=bot)
        if not result:
            return result
        assert isinstance(result, dict)
        command: aiogram.filters.CommandObject = result["command"]
        if not command.args:
            return False
        command_query = QueryDict(command.args)
        result.update(command_query=command_query)
        if self.query_magic:
            command_query_magic_result = self.query_magic.resolve(command_query)
            if not command_query_magic_result:
                return False
            if isinstance(command_query_magic_result, dict):
                result.update(command_query_magic_result)

        return result
