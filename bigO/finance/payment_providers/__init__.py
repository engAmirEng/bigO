from . import providers

__all__ = ["AVAILABLE_PAYMENT_PROVIDERS"]

AVAILABLE_PAYMENT_PROVIDERS = [
    providers.BankTransfer1,
]
