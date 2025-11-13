from datetime import timedelta

import humanize.filesize
import humanize.time
import pydantic
from django.utils.translation import gettext
from djmoney.money import Money
from moneyed import Currency

from bigO.utils.models import MakeInterval
from django.db.models import Case, DateTimeField, F, PositiveBigIntegerField, When
from django.db.models.functions import Cast, Now

from .base import BaseSubscriptionPlanProvider
from decimal import Decimal

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
                str(limit_bytes), humanize.precisedelta(timedelta(seconds=self.expiry_seconds)), str(m))

    PlanArgsModel = None

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
