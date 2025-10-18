from . import costproviders, planproviders

__all__ = ["AVAILABLE_SUBSCRIPTION_PLAN_PROVIDERS"]

AVAILABLE_SUBSCRIPTION_PLAN_PROVIDERS = [planproviders.TypeSimpleStrict1, planproviders.TypeSimpleDynamic1]
AVAILABLE_SUBSCRIPTION_PLAN_PRICE_PROVIDERS = [costproviders.TypeSimpleStrict1, costproviders.TypeSimpleDynamic1]
