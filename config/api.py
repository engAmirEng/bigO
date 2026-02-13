import rest_framework_api_key.models
from asgiref.sync import sync_to_async
from ninja import NinjaAPI
from ninja.security import APIKeyHeader

from bigO.node_manager.api import router as node_manager_router
from bigO.user_bot.api import router as user_bot_router


class APIKeyHeaderAuth(APIKeyHeader):
    param_name = "X-API-Key"

    async def authenticate(self, request, key):
        if not key:
            return None
        try:
            api_key = await sync_to_async(rest_framework_api_key.models.APIKey.objects.get_from_key)(key)
        except rest_framework_api_key.models.APIKey.DoesNotExist:
            return None
        if api_key.has_expired:
            return None
        return api_key


header_key_auth = APIKeyHeaderAuth()

api = NinjaAPI(title="AdminAPI", auth=header_key_auth)
api.add_router("/node-manager/", node_manager_router)
api.add_router("/user-bot/", user_bot_router)
