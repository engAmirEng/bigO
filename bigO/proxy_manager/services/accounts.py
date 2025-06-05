import logging

from django.db.models import Q
from django.utils import timezone

from .. import models

logger = logging.getLogger(__name__)


def get_connectable_subscriptionperiod_qs():
    return (
        models.SubscriptionPeriod.objects.ann_expires_at()
        .ann_dl_bytes_remained()
        .ann_up_bytes_remained()
        .filter(
            Q(selected_as_current=True, profile__is_active=True, expires_at__gt=timezone.now())
            & Q(Q(up_bytes_remained__gt=0) | Q(dl_bytes_remained__gt=0))
        )
    )


def get_agent_current_subscriptionperiods_qs(agent: models.Agent):
    return models.SubscriptionPeriod.objects.filter(
        profile__initial_agency_id=agent.agency_id, selected_as_current=True
    )
