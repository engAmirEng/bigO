from datetime import timedelta
from decimal import Decimal

import humanize.filesize
import humanize.time
import pydantic
from djmoney.money import Money
from moneyed import Currency

from bigO.utils.models import MakeInterval
from django.db.models import Case, DateTimeField, F, PositiveBigIntegerField, When
from django.db.models.functions import Cast, Now
from django.utils.translation import gettext

from .base import BaseSubscriptionPlanProvider


class TypeSimpleStrict1(BaseSubscriptionPlanProvider):
    TYPE_IDENTIFIER = "type_simple_strict1"

    class ProviderArgsModel(pydantic.BaseModel):
        total_usage_limit_bytes: int
        expiry_seconds: int
        price: Decimal

        def title(self, currency):
            limit_bytes = humanize.naturalsize(self.total_usage_limit_bytes)
            m = Money(amount=self.price, currency=currency)
            return f"{limit_bytes}/{humanize.precisedelta(timedelta(seconds=self.expiry_seconds))} {m}"

        def verbose_title(self, currency):
            limit_bytes = humanize.naturalsize(self.total_usage_limit_bytes)
            m = Money(amount=self.price, currency=currency)
            return "حجم {0} در مدت {1} با قیمت {2}".format(
                str(limit_bytes), humanize.precisedelta(timedelta(seconds=self.expiry_seconds)), str(m)
            )

    PlanArgsModel = None

    def calc_init_price(self):
        price_amount = self.provider_args.price
        price = Money(amount=price_amount, currency=self.currency)
        return price

    def get_total_limit_bytes(self):
        return self.provider_args.total_usage_limit_bytes

    @classmethod
    def get_expires_at_ann_expr(cls):
        a = MakeInterval(Cast("plan__plan_provider_args__expiry_seconds", PositiveBigIntegerField()))
        return Case(
            When(first_usage_at__isnull=False, then=F("first_usage_at") + a),
            default=Now() + a,
            output_field=DateTimeField(),
        )

    @classmethod
    def get_dl_bytes_remained_expr(cls):
        return (
            Cast("plan__plan_provider_args__total_usage_limit_bytes", PositiveBigIntegerField())
            - F("current_download_bytes")
            - F("current_upload_bytes")
        )

    @classmethod
    def get_up_bytes_remained_expr(cls):
        return (
            Cast("plan__plan_provider_args__total_usage_limit_bytes", PositiveBigIntegerField())
            - F("current_download_bytes")
            - F("current_upload_bytes")
        )

    @classmethod
    def get_total_limit_bytes_expr(cls):
        return Cast("plan__plan_provider_args__total_usage_limit_bytes", PositiveBigIntegerField())


class TypeSimpleDynamic1(BaseSubscriptionPlanProvider):
    TYPE_IDENTIFIER = "type_simple_dynamic1"

    class ProviderArgsModel(pydantic.BaseModel):
        per_gb_price: Decimal

        def title(self, currency: Currency):
            m = Money(amount=self.per_gb_price, currency=currency)
            return str(m) + " per GB"

        def verbose_title(self, currency):
            m = Money(amount=self.per_gb_price, currency=currency)
            return "{0} به ازای هر گیگابایت".format(m)

    class PlanArgsModel(pydantic.BaseModel):
        total_usage_limit_bytes: int
        expiry_seconds: int

        def title(self, currency):
            limit_bytes = humanize.naturalsize(self.total_usage_limit_bytes)
            return f"{limit_bytes}/{humanize.precisedelta(timedelta(seconds=self.expiry_seconds))}"

        def verbose_title(self):
            limit_bytes = humanize.naturalsize(self.total_usage_limit_bytes)
            return "حجم {0} در مدت {1}".format(
                str(limit_bytes), humanize.precisedelta(timedelta(seconds=self.expiry_seconds))
            )

    def calc_init_price(self):
        price_amount = (
            Decimal(self.plan_args.total_usage_limit_bytes / 1_000_000_000) * self.provider_args.per_gb_price
        )
        price = Money(amount=price_amount, currency=self.currency)
        return price

    def get_total_limit_bytes(self):
        return self.plan_args.total_usage_limit_bytes

    @classmethod
    def get_expires_at_ann_expr(cls):
        # a = ExpressionWrapper(
        #     Cast('plan_args__expiry_seconds', IntegerField()) * 1_000_000,  # Convert seconds to microseconds
        #     output_field=DurationField()
        # )
        a = MakeInterval(Cast("plan_args__expiry_seconds", PositiveBigIntegerField()))
        return Case(
            When(first_usage_at__isnull=False, then=F("first_usage_at") + a),
            default=Now() + a,
            output_field=DateTimeField(),
        )

    @classmethod
    def get_dl_bytes_remained_expr(cls):
        return (
            Cast("plan_args__total_usage_limit_bytes", PositiveBigIntegerField())
            - F("current_download_bytes")
            - F("current_upload_bytes")
        )

    @classmethod
    def get_up_bytes_remained_expr(cls):
        return (
            Cast("plan_args__total_usage_limit_bytes", PositiveBigIntegerField())
            - F("current_download_bytes")
            - F("current_upload_bytes")
        )

    @classmethod
    def get_total_limit_bytes_expr(cls):
        return Cast("plan_args__total_usage_limit_bytes", PositiveBigIntegerField())
