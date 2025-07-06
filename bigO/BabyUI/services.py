import uuid

from bigO.proxy_manager import models as proxy_manager_models
from django.contrib.auth import get_user_model
from django.db import transaction

User = get_user_model()


def create_new_user(
    agency: proxy_manager_models.Agency,
    agentuser: User,
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
    subscriptionevent = proxy_manager_models.SubscriptionEvent()
    subscriptionevent.related_agency = agency
    subscriptionevent.agentuser = agentuser
    subscriptionevent.profile = subscriptionprofile
    subscriptionevent.period = subscriptionperiod
    subscriptionevent.title = "New Profile Created"
    with transaction.atomic(using="main"):
        subscriptionprofile.save()
        subscriptionperiod.save()
        subscriptionevent.save()
        return subscriptionperiod


def renew_user(
    agency: proxy_manager_models.Agency,
    agentuser: User,
    plan: proxy_manager_models.SubscriptionPlan,
    plan_args: dict,
    profile: proxy_manager_models.SubscriptionProfile,
) -> proxy_manager_models.SubscriptionPeriod:
    subscriptionperiod = proxy_manager_models.SubscriptionPeriod()
    subscriptionperiod.profile = profile
    subscriptionperiod.plan = plan
    if plan.plan_provider_cls.PlanArgsModel:
        subscriptionperiod.plan_args = plan.plan_provider_cls.PlanArgsModel(**plan_args).model_dump()
    else:
        subscriptionperiod.plan_args = None
    subscriptionperiod.selected_as_current = True
    subscriptionevent = proxy_manager_models.SubscriptionEvent()
    subscriptionevent.related_agency = agency
    subscriptionevent.agentuser = agentuser
    subscriptionevent.profile = profile
    subscriptionevent.period = subscriptionperiod
    subscriptionevent.title = "Renew Profile"
    with transaction.atomic(using="main"):
        profile.periods.all().update(selected_as_current=False)
        subscriptionperiod.save()
        subscriptionevent.save()
        return subscriptionperiod


def suspend_user(profile: proxy_manager_models.SubscriptionProfile, agentuser: User):
    profile.is_active = False

    subscriptionevent = proxy_manager_models.SubscriptionEvent()
    subscriptionevent.related_agency = profile.initial_agency
    subscriptionevent.agentuser = agentuser
    subscriptionevent.profile = profile
    subscriptionevent.title = "Profile Suspended"

    with transaction.atomic(using="main"):
        profile.save()
        subscriptionevent.save()


def unsuspend_user(profile: proxy_manager_models.SubscriptionProfile, agentuser: User):
    profile.is_active = True

    subscriptionevent = proxy_manager_models.SubscriptionEvent()
    subscriptionevent.related_agency = profile.initial_agency
    subscriptionevent.agentuser = agentuser
    subscriptionevent.profile = profile
    subscriptionevent.title = "Profile Unsuspended"

    with transaction.atomic(using="main"):
        profile.save()
        subscriptionevent.save()
