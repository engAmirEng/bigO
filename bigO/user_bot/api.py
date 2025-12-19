from ninja import Router, Schema

from . import models, services

router = Router()


class TelegramMessageSchema(Schema):
    to_username: str
    text: str


@router.patch("/telegram/app/{app_id}/account/{account_id}/message")
async def patch_node(request, app_id: int, account_id: int, payload: TelegramMessageSchema):
    tapp = await models.TelegramApp.objects.aget(id=app_id)
    taccount = await models.TelegramAccount.objects.select_related("account_provider__telegram_bot").aget(
        id=account_id
    )
    client = await services.get_telegram_session(taccount=taccount, tapp=tapp)
    msg = await client.send_message(payload.to_username, message=payload.text)

    return {"success": True}
