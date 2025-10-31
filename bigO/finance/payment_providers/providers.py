import pydantic

from . import base


class BankTransfer1(base.BasePaymentProvider):
    TYPE_IDENTIFIER = "banktransfer1"

    class ProviderArgsModel(pydantic.BaseModel):
        card_number: str
        card_info: str

    class PaymentArgsModel(pydantic.BaseModel):
        verifier_user_id: int
