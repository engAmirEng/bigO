import datetime
import logging

from .. import models

logger = logging.getLogger(__name__)


def set_profile_last_stat(
    sub_profile_id: str, sub_profile_period_id: str, collect_time: datetime.datetime
) -> models.SubscriptionPeriod | None:
    subscriptionperiod = models.SubscriptionPeriod.objects.filter(
        id=sub_profile_period_id, profile_id=sub_profile_id
    ).first()
    if subscriptionperiod is None:
        logger.critical(f"no SubscriptionPeriod found with {sub_profile_id=} and {sub_profile_period_id=}")
        return None
    if subscriptionperiod.first_usage_at is None:
        subscriptionperiod.first_usage_at = collect_time
    if subscriptionperiod.first_usage_at > collect_time:
        subscriptionperiod.first_usage_at = collect_time

    if subscriptionperiod.last_usage_at is None:
        subscriptionperiod.last_usage_at = collect_time
    if subscriptionperiod.last_usage_at < collect_time:
        subscriptionperiod.last_usage_at = collect_time
    subscriptionperiod.save()
    return subscriptionperiod


def set_internal_user_last_stat(
    rule_id: str, node_user_id: str, collect_time: datetime.datetime
) -> models.InternalUser | None:
    internaluser = models.InternalUser.objects.filter(connection_rule_id=rule_id, node_id=node_user_id).first()
    if internaluser is None:
        logger.critical(f"no InternalUser found with {rule_id=} and {node_user_id=}")
        return
    if internaluser.first_usage_at is None:
        internaluser.first_usage_at = collect_time
    if internaluser.first_usage_at > collect_time:
        internaluser.first_usage_at = collect_time

    if internaluser.last_usage_at is None:
        internaluser.last_usage_at = collect_time
    if internaluser.last_usage_at < collect_time:
        internaluser.last_usage_at = collect_time
    internaluser.save()
    return internaluser
