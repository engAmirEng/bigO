from datetime import timedelta
from decimal import Decimal

import humanize.filesize
import humanize.time
import pydantic
import sentry_sdk
from djmoney.money import Money
from moneyed import Currency

from bigO.utils.models import MakeInterval
from django.db import transaction
from django.db.models import (
    Case,
    DateTimeField,
    DecimalField,
    F,
    OuterRef,
    PositiveBigIntegerField,
    Q,
    Subquery,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Cast, Floor, Now, Coalesce
from django.utils import timezone

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


class TypeSimpleAsYouGO1(BaseSubscriptionPlanProvider):
    TYPE_IDENTIFIER = "type_simple_as_you_go1"

    class ProviderArgsModel(pydantic.BaseModel):
        per_gb_price: Decimal
        pre_gb_pay: int
        min_credit_charge: Decimal

        def title(self, currency: Currency):
            m = Money(amount=self.per_gb_price, currency=currency)
            return str(m) + " per GB"

        def verbose_title(self, currency):
            m = Money(amount=self.per_gb_price, currency=currency)
            return "{0} به ازای هر گیگابایت".format(m)

    class PlanArgsModel(pydantic.BaseModel):
        paid_bytes: int

        def title(self, currency):
            return None

        def verbose_title(self):
            return None

    def calc_init_price(self):
        price_amount = Decimal(self.provider_args.pre_gb_pay) * self.provider_args.per_gb_price
        price = Money(amount=price_amount, currency=self.currency)
        return price

    @classmethod
    def get_expires_at_ann_expr(cls):
        return Value(None)

    @classmethod
    def remained_xpr(cls):
        from .. import models

        qs = (
            models.MemberCredit.objects.filter(
                Q(agency_user__user=OuterRef("profile__user"), agency_user__agency=OuterRef("profile__initial_agency"))
            )
            .ann_currency()
            .filter(currency=OuterRef("plan__base_currency"))
            .order_by()
            .values("agency_user")
            .annotate(balance=Sum("credit") - Sum("debt"))
        )
        return (
            Cast("plan_args__paid_bytes", PositiveBigIntegerField())
            + (
                Floor(
                    Coalesce(Subquery(qs.values("balance")), Value(0))
                    / Cast("plan__plan_provider_args__per_gb_price", DecimalField(max_digits=10, decimal_places=2))
                )
                * Value(1000_000_000)
            )
            - F("current_download_bytes")
            - F("current_upload_bytes")
        )

    @classmethod
    def get_dl_bytes_remained_expr(cls):
        return cls.remained_xpr()

    @classmethod
    def get_up_bytes_remained_expr(cls):
        return cls.remained_xpr()

    @classmethod
    def get_total_limit_bytes_expr(cls):
        from .. import models

        qs = (
            models.MemberCredit.objects.filter(
                Q(agency_user__user=OuterRef("profile__user"), agency_user__agency=OuterRef("profile__initial_agency"))
                & Q(
                    Q(credit_currency=OuterRef("plan__base_currency"))
                    | Q(debt_currency=OuterRef("plan__base_currency"))
                )
            )
            .order_by()
            .values("agency_user")
            .annotate(balance=Sum("credit") - Sum("debt"))
        )
        return Cast("plan_args__paid_bytes", PositiveBigIntegerField()) + (
            Floor(
                Subquery(qs.values("balance"))
                / Cast("plan__plan_provider_args__per_gb_price", DecimalField(max_digits=10, decimal_places=2))
            )
            * Value(1000_000_000)
        )

    @classmethod
    def check_use_credit(cls):
        from .. import models

        result = []
        subscriptionperiod_qs = (
            models.SubscriptionPeriod.objects.filter(plan__plan_provider_key=cls.TYPE_IDENTIFIER)
            .annotate(
                total_used_bytes=F("current_download_bytes") + F("current_upload_bytes"),
                not_paid_bytes=F("total_used_bytes") - Cast("plan_args__paid_bytes", PositiveBigIntegerField()),
                not_paid_credit=F("not_paid_bytes")
                * Cast("plan__plan_provider_args__per_gb_price", DecimalField(max_digits=10, decimal_places=2)),
            )
            .filter(
                not_paid_credit__gt=Cast(
                    "plan__plan_provider_args__min_credit_charge", DecimalField(max_digits=10, decimal_places=2)
                )
            )
        )
        for subscriptionperiod in subscriptionperiod_qs:
            agency_user = models.AgencyUser.objects.filter(
                agency=subscriptionperiod.profile.initial_agency, user=subscriptionperiod.profile.user
            ).first()
            if agency_user is None:
                sentry_sdk.capture_message(f"check_use_credit: no agency user found for {subscriptionperiod.profile}")
                continue

            balance = models.MemberCredit.objects.filter(
                Q(
                    agency_user__user=subscriptionperiod.profile.user,
                    agency_user__agency=subscriptionperiod.profile.initial_agency,
                )
                & Q(
                    Q(credit_currency=OuterRef("plan__base_currency"))
                    | Q(debt_currency=OuterRef("plan__base_currency"))
                )
            ).aggregate(balance=Sum("credit") - Sum("debt"))["balance"]

            providerarg = cls.ProviderArgsModel(**subscriptionperiod.plan.plan_provider_args)
            charging_credit_value = providerarg.min_credit_charge
            not_paid_gb = subscriptionperiod.not_paid_bytes // 1000_000_000
            if not_paid_gb:
                charging_credit_value = not_paid_gb * providerarg.per_gb_price
            charging_credit = Money(amount=charging_credit_value, currency=subscriptionperiod.plan.base_currency)
            charging_bytes = int(charging_credit_value / providerarg.per_gb_price * 1000_000_000)

            membercredit = models.MemberCredit()
            membercredit.agency_user = agency_user
            membercredit.debt = charging_credit
            membercredit.created_by = subscriptionperiod.profile.user
            description = "use credit for plan"
            membercredit.description = description

            subscriptionperiodcreditusage = models.SubscriptionPeriodCreditUsage()
            subscriptionperiodcreditusage.credit = membercredit
            subscriptionperiodcreditusage.period = subscriptionperiodcreditusage

            plan_arg = cls.PlanArgsModel(**subscriptionperiod.plan_args)
            plan_arg.paid_bytes += charging_bytes
            subscriptionperiod.plan_args = plan_arg.model_dump()
            if balance - charging_credit <= 0:
                subscriptionperiod.limited_at = timezone.now()
            else:
                subscriptionperiod.limited_at = None
            with transaction.atomic():
                membercredit.save()
                subscriptionperiodcreditusage.save()
                subscriptionperiod.save()

            result.append(
                {
                    "subscriptionperiod": subscriptionperiod,
                    "used_credit": charging_credit,
                    "charging_bytes": charging_bytes,
                    "wallet_credit": balance,
                }
            )
