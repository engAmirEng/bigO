import logging

from django.db.models import Q
from django.utils import timezone

from .. import models

logger = logging.getLogger(__name__)


def get_connectable_subscriptionperiod_qs():
    return models.SubscriptionPeriod.objects.ann_limit_passed_type().filter(
        Q(limit_passed_type__isnull=True, selected_as_current=True, profile__is_active=True)
    )


def get_agent_current_subscriptionperiods_qs(agent: models.Agent):
    return models.SubscriptionPeriod.objects.filter(
        profile__initial_agency_id=agent.agency_id, selected_as_current=True
    )


def get_agent_current_subscriptionprofiled_qs(agent: models.Agent):
    return models.SubscriptionProfile.objects.filter(initial_agency_id=agent.agency_id)
