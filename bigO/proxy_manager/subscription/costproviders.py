import pydantic
from decimal import Decimal
from .base import BaseSubscriptionPlanPriceProvider, BaseSubscriptionPlanProvider


class TypeSimpleStrict1(BaseSubscriptionPlanPriceProvider):
    TYPE_IDENTIFIER = "type_simple_strict1"

    class ProviderArgsModel(pydantic.BaseModel):
        priceunits: Decimal
        prepay_priceunits: Decimal

    PlanArgsModel = None

    def get_priceunits(self, plan_provider: BaseSubscriptionPlanProvider):
        return self.provider_args.priceunits

    def get_prepay_priceunits(self, plan_provider: BaseSubscriptionPlanProvider):
        return self.provider_args.prepay_priceunits


class TypeSimpleDynamic1(BaseSubscriptionPlanPriceProvider):
    TYPE_IDENTIFIER = "type_simple_dynamic1"

    class ProviderArgsModel(pydantic.BaseModel):
        per_gigabyte_priceunits: Decimal
        prepay_percent: Decimal

    def get_priceunits(self, plan_provider: BaseSubscriptionPlanProvider):
        return self.provider_args.per_gigabyte_priceunits * plan_provider.get_total_limit_bytes() / 1000_000

    def get_prepay_priceunits(self, plan_provider: BaseSubscriptionPlanProvider):
        return self.provider_args.prepay_percent * self.get_priceunits(plan_provider)
