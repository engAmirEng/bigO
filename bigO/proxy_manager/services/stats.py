import datetime
import logging

import influxdb_client
import sentry_sdk

from bigO.node_manager import models as node_manager_models

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


def set_outbound_delay_tags(*, point: influxdb_client.Point, node: node_manager_models.Node, outbound_name: str):
    from . import XrayOutBound

    res = XrayOutBound.parse_outbound_name(node=node, name=outbound_name)
    if res is None:
        return
    point.tag("connection_name", outbound_name)
    if res is None:
        sentry_sdk.capture_message(f"could not find {outbound_name=}")
    elif isinstance(res, models.ConnectionRuleOutbound):
        if res.is_reverse:
            if str(res.connector.dest_node_id) == str(node.id):
                point.tag("connection_type", "reverse_interconn")
                point.tag("source_node_id", str(res.connector.dest_node_id))
                point.tag("dest_node_id", str(res.portal_node_id))
            elif str(res.portal_node_id) == str(node.id):
                point.tag("connection_type", "reverse")
                point.tag("source_node_id", str(res.portal_node_id))
                point.tag("dest_node_id", str(res.connector.dest_node_id))
            else:
                raise NotImplementedError

            point.tag("connection_rule_id", str(res.rule_id))
        else:
            point.tag("connection_type", "node_outbound")
            point.tag("source_node_id", str(res.portal_node_id))
            point.tag("connection_rule_id", str(res.rule_id))
    elif isinstance(res, models.ConnectionTunnelOutbound):
        point.tag("connectiontunnel_id", str(res.tunnel_id))
        if res.is_reverse:
            if res.tunnel.dest_node == node:
                point.tag("connection_type", "tunnel_reverse_interconn")
                point.tag("source_node_id", str(res.tunnel.dest_node_id))
                point.tag("dest_node_id", str(res.tunnel.source_node_id))
            elif res.tunnel.source_node == node:
                point.tag("connection_type", "tunnel_reverse")
                point.tag("source_node_id", str(res.tunnel.source_node_id))
                point.tag("dest_node_id", str(res.connector.dest_node_id))
                # == point.tag("dest_node_id", str(res.tunnel.dest_node_id))
            else:
                raise NotImplementedError
        else:
            point.tag("connection_type", "tunnel_outbound")
            point.tag("source_node_id", str(res.tunnel.source_node_id))
            point.tag("dest_node_id", str(res.tunnel.dest_node_id))
    else:
        raise NotImplementedError
