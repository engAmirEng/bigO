import datetime
import json
import logging
from typing import TypedDict

import influxdb_client
import sentry_sdk

from bigO.node_manager import models as node_manager_models
from django.conf import settings
from django.core.cache import cache
from django.core.cache.utils import make_template_fragment_key
from django.utils import timezone

from .. import models

logger = logging.getLogger(__name__)


def set_outbound_tags(
    *,
    point: influxdb_client.Point,
    node: node_manager_models.Node,
    outbound_name: str,
    store: dict[str, models.ConnectionRuleOutbound | models.ConnectionTunnelOutbound | None] | None = None,
) -> models.ConnectionRuleOutbound | models.ConnectionTunnelOutbound | None:
    from . import XrayOutBound

    if store:
        key = f"{node.id}.{outbound_name}"
        try:
            res = store[key]
        except KeyError:
            res = XrayOutBound.parse_outbound_name(node=node, name=outbound_name)
            store[key] = res
    else:
        res = XrayOutBound.parse_outbound_name(node=node, name=outbound_name)
    if res is None:
        return
    point.tag("connection_name", outbound_name)
    if res is None:
        sentry_sdk.capture_message(f"could not find {outbound_name=}")
    elif isinstance(res, models.ConnectionRuleOutbound):
        point.tag("connection_outbound_id", str(res.id))
        point.tag("connection_rule_id", str(res.rule_id))
        point.tag("connector_id", str(res.connector_id))
        point.tag("outbound_type_id", str(res.connector.outbound_type_id))
        if res.connector.inbound_spec_id:
            point.tag("inbound_spec_id", str(res.connector.inbound_spec_id))
        if res.connector.outbound_type.to_inbound_type_id:
            point.tag("inbound_type_id", str(res.connector.outbound_type.to_inbound_type_id))
        if res.is_reverse:
            bridge_node = res.get_bridge_node()
            portal_node = res.get_portal_node()
            if bridge_node == node:
                point.tag("connection_type", "reverse_interconn")
                point.tag("source_node_id", str(bridge_node.id))
                point.tag("dest_node_id", str(portal_node.id))
            elif portal_node == node:
                point.tag("connection_type", "reverse")
                point.tag("source_node_id", str(portal_node.id))
                point.tag("dest_node_id", str(bridge_node.id))
            else:
                raise NotImplementedError
        else:
            point.tag("connection_type", "node_outbound")
            point.tag("source_node_id", str(res.apply_node_id))
            if res.connector.dest_node:
                point.tag("dest_node_id", str(res.connector.dest_node_id))
    elif isinstance(res, models.ConnectionTunnelOutbound):
        point.tag("connection_outbound_id", str(res.id))
        point.tag("connectiontunnel_id", str(res.tunnel_id))
        point.tag("connector_id", str(res.connector_id))
        point.tag("outbound_type_id", str(res.connector.outbound_type_id))
        if res.connector.inbound_spec_id:
            point.tag("inbound_spec_id", str(res.connector.inbound_spec_id))
        if res.connector.outbound_type.to_inbound_type_id:
            point.tag("inbound_type_id", str(res.connector.outbound_type.to_inbound_type_id))
        if res.is_reverse:
            bridge_node = res.get_bridge_node()
            portal_node = res.get_portal_node()
            if bridge_node == node:
                point.tag("connection_type", "tunnel_reverse_interconn")
                point.tag("source_node_id", str(bridge_node.id))
                point.tag("dest_node_id", str(portal_node.id))
            elif portal_node == node:
                point.tag("connection_type", "tunnel_reverse")
                point.tag("source_node_id", str(portal_node.id))
                point.tag("dest_node_id", str(bridge_node.id))
                # == point.tag("dest_node_id", str(res.tunnel.dest_node_id))
            else:
                raise NotImplementedError
        else:
            point.tag("connection_type", "tunnel_outbound")
            point.tag("source_node_id", str(res.tunnel.source_node_id))
            point.tag("dest_node_id", str(res.tunnel.dest_node_id))
    else:
        raise NotImplementedError
    return res


def get_connection_outbound_latest_delays(
    _type: type[models.ConnectionRuleOutbound] | type[models.ConnectionTunnelOutbound], ids: list[int] | None = None
) -> dict[str, dict]:
    time = timezone.now() - datetime.timedelta(minutes=10)
    ids = ids or []
    cache_key = make_template_fragment_key("outbound_delays", [str(_type), *ids])
    cache_res = cache.get(cache_key)
    if cache_res:
        res = json.loads(cache_res)
        return res
    ids_filter = ""
    if ids:
        ids_filter = "|> filter(fn: (r) => {})".format(
            " or ".join([f'r["connection_outbound_id"] == "{i}"' for i in ids])
        )
    if _type == models.ConnectionRuleOutbound:
        query = f"""
from(bucket: "{settings.INFLUX_BUCKET}")
|> range(start: {time.strftime('%Y-%m-%dT%H:%M:%SZ')})
|> filter(fn: (r) => r["_measurement"] == "connection_health")
|> filter(fn: (r) => r["_field"] == "delay")
|> filter(fn: (r) => r["connection_type"] == "node_outbound" or r["connection_type"] == "reverse")
{ids_filter}
"""
    elif _type == models.ConnectionTunnelOutbound:
        query = f"""
        from(bucket: "{settings.INFLUX_BUCKET}")
        |> range(start: {time.strftime('%Y-%m-%dT%H:%M:%SZ')})
        |> filter(fn: (r) => r["_measurement"] == "connection_health")
        |> filter(fn: (r) => r["_field"] == "delay")
        |> filter(fn: (r) => r["connection_type"] == "tunnel_outbound" or r["connection_type"] == "tunnel_reverse")
        {ids_filter}
        """
    else:
        raise NotImplementedError

    class _3(TypedDict):
        connection_name: str
        _value: float

    class _2:
        values: _3

    class _1:
        records: list[_2]

    df: list[_1] = (
        influxdb_client.InfluxDBClient(url=settings.INFLUX_URL, token=settings.INFLUX_TOKEN, org=settings.INFLUX_ORG)
        .query_api()
        .query(query)
    )
    res = {}
    for i in df:
        j = i.records[0].values
        res[j["connection_outbound_id"]] = {
            "id": j["connection_outbound_id"],
            "delay_list": [int(r.values["_value"]) for r in i.records],
        }
    cache.set(cache_key, json.dumps(res), 20)
    return res
