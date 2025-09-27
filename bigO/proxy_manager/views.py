import base64
import logging
import random
import uuid

import sentry_sdk
from asgiref.sync import sync_to_async

import django.template
import django.urls.resolvers
from bigO.utils import py_helpers
from django.http import Http404, HttpResponse
from django.utils import timezone

from . import models, typing

logger = logging.getLogger(__name__)


async def sublink_view(request, subscription_uuid: uuid.UUID):
    # todo save stats
    try:
        subscriptionprofile_obj = await models.SubscriptionProfile.objects.select_related("initial_agency").aget(
            uuid=subscription_uuid
        )
    except models.SubscriptionProfile.DoesNotExist:
        raise Http404()
    subscriptionperiod_obj = (
        await subscriptionprofile_obj.periods.filter(selected_as_current=True)
        .select_related("plan__connection_rule")
        .ann_expires_at()
        .ann_up_bytes_remained()
        .ann_dl_bytes_remained()
        .ann_total_limit_bytes()
        .afirst()
    )
    if subscriptionperiod_obj is None:
        return "todo"
    subscriptionperiod_obj.last_sublink_at = timezone.now()
    await subscriptionperiod_obj.asave()
    res_lines = []
    sublink_header_content = django.template.Template(
        subscriptionprofile_obj.initial_agency.sublink_header_template
    ).render(context=django.template.Context({"subscriptionperiod_obj": subscriptionperiod_obj}))
    res_lines.append(sublink_header_content)

    connection_rule = subscriptionperiod_obj.plan.connection_rule
    if connection_rule.inbound_choose_rule is None:
        return "todo"
    inbound_choose_rule = typing.InboundChooseRuleSchema(**connection_rule.inbound_choose_rule)
    rule_specs = (
        models.ConnectionRuleInboundSpec.objects.filter(rule=subscriptionperiod_obj.plan.connection_rule)
        .select_related(
            "spec__inbound_type",
            "spec__domain_address__domain",
            "spec__ip_address",
            "spec__domain_sni",
            "spec__domainhost_header",
        )
        .select_related(
            "connector__outbound_type__to_inbound_type",
            "connector__inbound_spec__domain_address__domain",
            "connector__inbound_spec__ip_address",
            "connector__inbound_spec__domain_sni",
            "connector__inbound_spec__domainhost_header",
        )
    )
    rule_specs = [i async for i in rule_specs]
    config = await sync_to_async(models.Config.get_solo)()
    for in_rule in inbound_choose_rule.inbounds:
        related_rule_specs = [i for i in rule_specs if i.key == in_rule.key_name if i.weight > 0]
        if not related_rule_specs:
            continue
        selected_rule_specs: list[models.ConnectionRuleInboundSpec] = random.choices(
            related_rule_specs, weights=[i.weight for i in related_rule_specs], k=in_rule.count
        )
        for counter in range(in_rule.count):
            selected_rule_spec = selected_rule_specs[counter]
            is_old_style = not bool(selected_rule_spec.connector)
            selected_spec: models.InboundSpec | None = (
                selected_rule_spec.spec if is_old_style else selected_rule_spec.connector.inbound_spec
            )
            if selected_spec is None:
                if config.sublink_debug:
                    res_lines.append(f"#skipping connection_rule_spec_id: {selected_rule_spec} has no inbound_spec")
                continue
            inbound_type: models.InboundType | None = (
                selected_spec.inbound_type
                if is_old_style
                else selected_rule_spec.connector.outbound_type.to_inbound_type
            )
            if inbound_type is None:
                if config.sublink_debug:
                    res_lines.append(f"#skipping connection_rule_spec_id: {selected_rule_spec} has no inbound_type")
                continue
            link_template = inbound_type.link_template
            combo_stat = await sync_to_async(selected_spec.get_combo_stat)()
            remark_prefix = (
                (subscriptionperiod_obj.plan.connection_rule.inbound_remarks_prefix or "")
                + in_rule.prefix
                + f"({selected_spec.id}-{counter})"
            )
            link_res = await sync_to_async(django.template.Template(link_template).render)(
                context=django.template.Context(
                    {
                        "subscriptionperiod_obj": subscriptionperiod_obj,
                        "combo_stat": combo_stat,
                        "remark_prefix": remark_prefix,
                        "connection_rule": subscriptionperiod_obj.plan.connection_rule,
                    }
                )
            )
            if not link_res:
                if config.sublink_debug:
                    res_lines.append(f"#skipping connection_rule_spec_id: {selected_rule_spec} is empty")
                continue
            if "templateerror" in link_res:
                if config.sublink_debug:
                    res_lines.append(
                        f"#skipping connection_rule_spec_id: {selected_rule_spec} becuase of templateerror"
                    )
                sentry_sdk.capture_message(
                    f"templateerror in connection_rule_spec_id: {selected_rule_spec} and {subscriptionperiod_obj=}"
                )
                continue
            res_lines.append(link_res)

    sublink_content = "\n".join(res_lines)

    if request.GET.get("base64"):
        sublink_content = base64.b64encode(sublink_content.encode())

    return HttpResponse(sublink_content, content_type="text/plain; charset=utf-8")


async def dynamic_sublink_view(request, sublink_path: str):
    pattern = django.urls.resolvers.RoutePattern(route="change-me/todo/<uuid:subscription_uuid>")
    match = pattern.match(path=sublink_path.rstrip("/"))
    if match is None:
        pattern = django.urls.resolvers.RoutePattern(route="sub/<uuid:subscription_uuid>")
        match = pattern.match(path=sublink_path.rstrip("/"))
        if match is None:
            raise django.urls.Resolver404()
    return await sublink_view(request, **match[2])
