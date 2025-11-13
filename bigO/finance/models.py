import datetime
import uuid

from djmoney.models.fields import MoneyField
from polymorphic.models import PolymorphicModel

from bigO.finance.payment_providers import AVAILABLE_PAYMENT_PROVIDERS
from bigO.finance.payment_providers.base import BasePaymentProvider
from bigO.proxy_manager.subscription import AVAILABLE_SUBSCRIPTION_PLAN_PROVIDERS
from bigO.proxy_manager.subscription.base import BaseSubscriptionPlanProvider
from bigO.users.models import User
from bigO.utils.models import TimeStampedModel
from django.db import models
from django.db.models import Case, Count, F, OuterRef, Q, Subquery, UniqueConstraint, When
from django.db.models.functions import Coalesce


class Invoice(TimeStampedModel, PolymorphicModel, models.Model):
    class StatusChoices(models.IntegerChoices):
        DRAFT = 0, "Draft"
        ISSUED = 1, "Issued"
        PAID = 2, "Paid"
        CANCELLED = 3, "Cancelled"

    uuid = models.UUIDField(default=uuid.uuid4)
    total_price = MoneyField(max_digits=14, decimal_places=2, default_currency="USD")
    due_date = models.DateTimeField(null=True, blank=True)
    status = models.PositiveSmallIntegerField(choices=StatusChoices.choices)

    def __str__(self):
        return f"{self.id}-{self.get_status_display()}({self.total_price})"


class InvoiceItem(TimeStampedModel, PolymorphicModel, models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="items")
    total_price = MoneyField(max_digits=14, decimal_places=2, default_currency="USD")


class Payment(TimeStampedModel, models.Model):
    uuid = models.UUIDField(default=uuid.uuid4)
    provider = models.ForeignKey("PaymentProvider", on_delete=models.PROTECT, related_name="+")
    provider_args = models.JSONField(null=True, blank=True)
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="+")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    amount = MoneyField(max_digits=14, decimal_places=2, default_currency="USD")
    payment_date = models.DateTimeField()
    status = models.CharField(
        max_length=20,
        choices=[
            ("pending", "Pending"),
            ("completed", "Completed"),
            ("failed", "Failed"),
            ("refunded", "Refunded"),
        ],
        default="pending",
    )


class PaymentProvider(TimeStampedModel, models.Model):
    name = models.SlugField(unique=True)
    provider_key = models.SlugField(max_length=127, db_index=True)
    provider_args = models.JSONField(null=True, blank=True)

    def __str__(self):
        return f"{self.pk}-{self.name}"

    @property
    def provider_cls(self) -> type[BasePaymentProvider]:
        return [i for i in AVAILABLE_PAYMENT_PROVIDERS if i.TYPE_IDENTIFIER == self.provider_key][0]

    def get_provider(self) -> BasePaymentProvider:
        return self.provider_cls(args=self.provider_args)


class Refund(TimeStampedModel, models.Model):
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name="refunds")
    amount = MoneyField(max_digits=14, decimal_places=2, default_currency="USD")
    reason = models.TextField(blank=True)
