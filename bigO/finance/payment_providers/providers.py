import hashlib
from typing import TYPE_CHECKING

import pydantic
from moneyed import Money

from django.db.models import QuerySet
from django.dispatch import Signal

from ...users.models import User
from . import base

if TYPE_CHECKING:
    from .. import models


class BankTransfer1(base.BasePaymentProvider):
    TYPE_IDENTIFIER = "banktransfer1"

    class ProviderArgsModel(pydantic.BaseModel):
        card_number: str
        card_info: str
        counter_base: int

    class PaymentArgsModel(pydantic.BaseModel):
        verifier_user_id: int

    pend_request = Signal()

    @classmethod
    def get_price(cls, identifier: str, price: Money, provider_args: ProviderArgsModel | None):
        hs = hashlib.sha256(identifier.encode()).hexdigest()
        hs_int = int(hs, 16)
        hs_money_amount = hs_int % provider_args.counter_base
        return price + Money(amount=hs_money_amount, currency=price.currency)

    @classmethod
    async def pend(cls, admins: QuerySet[User], payment: "models.Payment"):
        counter = 0
        async for admin in admins.order_by("?"):
            if counter >= 3:
                break
            await cls.pend_request.asend(sender=cls, admin=admin, payment=payment)
            counter += 1
        if counter == 0:
            raise Exception("no admins set for this provider")
