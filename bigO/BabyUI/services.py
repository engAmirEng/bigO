import uuid

from bigO.proxy_manager import models as proxy_manager_models
from django.db import transaction


def create_new_user(
    agency: proxy_manager_models.Agency,
    plan: proxy_manager_models.SubscriptionPlan,
    title: str,
    plan_args: dict,
    description: str | None = None,
) -> proxy_manager_models.SubscriptionPeriod:
    subscriptionprofile = proxy_manager_models.SubscriptionProfile()
    subscriptionprofile.initial_agency = agency
    subscriptionprofile.title = title
    subscriptionprofile.uuid = uuid.uuid4()
    subscriptionprofile.xray_uuid = uuid.uuid4()
    subscriptionprofile.description = description
    subscriptionprofile.is_active = True
    subscriptionperiod = proxy_manager_models.SubscriptionPeriod()
    subscriptionperiod.profile = subscriptionprofile
    subscriptionperiod.plan = plan
    if plan.plan_provider_cls.PlanArgsModel:
        subscriptionperiod.plan_args = plan.plan_provider_cls.PlanArgsModel(**plan_args).model_dump()
    else:
        subscriptionperiod.plan_args = None
    subscriptionperiod.selected_as_current = True
    with transaction.atomic(using="main"):
        subscriptionprofile.save()
        subscriptionperiod.save()
        return subscriptionperiod
