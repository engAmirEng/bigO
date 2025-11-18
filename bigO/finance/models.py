import datetime
import uuid
from typing import Any

from djmoney.models.fields import MoneyField
from moneyed import Money
from polymorphic.models import PolymorphicModel

from bigO.finance.payment_providers import AVAILABLE_PAYMENT_PROVIDERS
from bigO.finance.payment_providers.base import BasePaymentProvider
from bigO.proxy_manager.subscription import AVAILABLE_SUBSCRIPTION_PLAN_PROVIDERS
from bigO.proxy_manager.subscription.base import BaseSubscriptionPlanProvider
from bigO.users.models import User
from bigO.utils.models import TimeStampedModel
from django.db import models, transaction
from django.db.models import Case, Count, F, OuterRef, Q, Subquery, UniqueConstraint, When
from django.db.models.functions import Coalesce


class Invoice(TimeStampedModel, PolymorphicModel, models.Model):
    class StatusChoices(models.IntegerChoices):
        DRAFT = 0, "Draft"
        ISSUED = 1, "Issued"
        PAID = 2, "Paid"
        CANCELLED = 3, "Cancelled"

    uuid = models.UUIDField(default=uuid.uuid4, unique=True)
    total_price = MoneyField(max_digits=14, decimal_places=2, default_currency="USD")
    due_date = models.DateTimeField(null=True, blank=True)
    status = models.PositiveSmallIntegerField(choices=StatusChoices.choices)

    def __str__(self):
        return f"{self.id}-{self.get_status_display()}({self.total_price})"

    def calc_price(self, items):
        result = 0
        for i in items:
            result += i.calc_price()
        return result

    def redo(self):
        changed = False
        items = []
        for i in self.items.all():
            items.append(i)
            price = i.calc_price()
            if i.total_price != price:
                i.total_price = price
                changed &= changed
        new_price = self.calc_price(items=items)
        self.total_price = new_price
        with transaction.atomic():
            self.save()
            [i.save() for i in items]
        return changed


class InvoiceItem(TimeStampedModel, PolymorphicModel, models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="items")
    total_price = MoneyField(max_digits=14, decimal_places=2, default_currency="USD")
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    issued_to: Any

    def __str__(self):
        return f"{self.id}-item of invoice_id={self.invoice_id}({self.total_price})"

    def calc_price(self):
        raise NotImplementedError


class Payment(TimeStampedModel, models.Model):
    class PaymentStatusChoices(models.IntegerChoices):
        INITIATED = 1, "Initiated"
        PENDING = 2, "Pending"
        COMPLETED = 3, "Completed"
        FAILED = 4, "Failed"
        REFUNDED = 5, "Refunded"

    uuid = models.UUIDField(default=uuid.uuid4)
    provider = models.ForeignKey("PaymentProvider", on_delete=models.PROTECT, related_name="+")
    provider_args = models.JSONField(null=True, blank=True)
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="+")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    amount = MoneyField(max_digits=14, decimal_places=2, default_currency="USD")
    completed_at = models.DateTimeField(null=True, blank=True)
    status = models.PositiveSmallIntegerField(
        choices=PaymentStatusChoices.choices, default=PaymentStatusChoices.PENDING
    )

    @classmethod
    def init_payment(cls, invoice: Invoice, provider: "PaymentProvider", user: User):
        price = provider.get_price(invoice=invoice)

        obj = cls()
        obj.uuid = uuid.uuid4()
        obj.provider = provider
        obj.provider_args = "payment_args"
        obj.invoice = invoice
        obj.user = user
        obj.amount = price
        obj.status = cls.PaymentStatusChoices.INITIATED
        obj.save()
        return obj


class PaymentProvider(TimeStampedModel, models.Model):
    name = models.SlugField(unique=True)
    provider_key = models.SlugField(max_length=127, db_index=True)
    provider_args = models.JSONField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.pk}-{self.name}"

    @property
    def provider_cls(self) -> type[BasePaymentProvider]:
        return [i for i in AVAILABLE_PAYMENT_PROVIDERS if i.TYPE_IDENTIFIER == self.provider_key][0]

    def get_provider_args(self) -> BasePaymentProvider | None:
        if self.provider_cls is None:
            return None
        return self.provider_cls.ProviderArgsModel(**self.provider_args)

    def get_price(self, invoice: Invoice):
        idf = invoice.id % 100
        return invoice.total_price + Money(amount=idf, currency=invoice.total_price.currency)


class Refund(TimeStampedModel, models.Model):
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name="refunds")
    amount = MoneyField(max_digits=14, decimal_places=2, default_currency="USD")
    reason = models.TextField(blank=True)
