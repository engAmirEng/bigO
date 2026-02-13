import bigO.proxy_manager.utils

from . import utils


def get_telethon_client(session_obj):
    proxy_resource = bigO.proxy_manager.utils.Xray2HttpProxyResource()

    session = utils.Session(session=session_obj)
    client = utils.TelegramClient(
        session, session_obj.app.api_id, session_obj.app.api_hash, proxy_resource=proxy_resource
    )
    return client
