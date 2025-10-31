import json
import random
import string

from bigO.proxy_manager import models as proxy_manager_models
from bigO.telegram_bot import models as telegram_bot_models
from bigO.users.models import User
from django.core.cache import cache

from . import models


class TelegramBotNotSet(Exception):
    pass


def get_user_startlink(bot_obj: telegram_bot_models.TelegramBot, user: User, transfer_ownership: bool = False) -> str:
    from .dispatchers import QueryPathName, get_dispatch_query

    key = set_secret_key(data={"user_id": user.id, "transfer_ownership": transfer_ownership}, length=10)
    link = get_dispatch_query(bot_username=bot_obj.tusername, pathname=QueryPathName.ASSOCIATE_TO_USER, key=key)
    return link


def get_subscription_profile_startlink(
    bot_obj: telegram_bot_models.TelegramBot,
    subscription_profile: proxy_manager_models.SubscriptionProfile,
    transfer_ownership: bool = False,
) -> str:
    from .dispatchers import QueryPathName, get_dispatch_query

    key = set_secret_key(
        data={"subscription_profile_id": subscription_profile.id, "transfer_ownership": transfer_ownership}, length=10
    )
    link = get_dispatch_query(bot_username=bot_obj.tusername, pathname=QueryPathName.ASSOCIATE_TO_ACCOUNT, key=key)
    return link


def set_secret_key(data: dict, length: int) -> str:
    allowed_characters = string.ascii_letters + string.digits + "-" + "_"
    secret_key = "".join(random.choice(allowed_characters) for _ in range(length))
    json_data = json.dumps(data)
    cache.set(secret_key, json_data, timeout=24 * 60 * 60)
    return secret_key


async def get_secret_key(secret_key: str) -> dict | None:
    json_data = await cache.aget(secret_key)
    if json_data is None:
        return
    data = json.loads(json_data)
    return data


async def make_username(base=None, length=15) -> str:
    if base:
        base = f"{base}-"
    else:
        base = ""
    length -= len(base)
    characters = string.ascii_letters + string.digits
    while True:
        username = base + "".join(random.choice(characters) for _ in range(length))
        if not await User.objects.filter(username=username).aexists():
            return username
