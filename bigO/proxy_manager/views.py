import base64
import logging
import random
import uuid

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
        .select_related("plan__connection_rule__inboundcombogroup")
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

    if (inboundcombogroup := subscriptionperiod_obj.plan.connection_rule.inboundcombogroup) is None:
        logger.error(f"no inboundcombogroup is set for {subscriptionperiod_obj.plan.connection_rule=}")
        raise Http404()

    async for inboundcombochoicegroup in models.InboundComboChoiceGroup.objects.filter(
        group=inboundcombogroup
    ).select_related("combo__inbound_type").order_by("ordering"):
        combo = inboundcombochoicegroup.combo
        link_template = combo.inbound_type.link_template

        domain_addresses = [
            (i.domain.name, i.weight) async for i in combo.domainaddresses.select_related("domain").all()
        ]
        ip_addresses = [(str(i.ip.ip.ip), i.weight) async for i in combo.ipaddresses.select_related("ip").all()]
        all_addressed = [*domain_addresses, *ip_addresses]

        ports = combo.ports.split(",")

        domain_snis = [(i.domain.name, i.weight) async for i in combo.domainsnis.select_related("domain").all()]

        domainhostheaders = [
            (i.domain.name, i.weight) async for i in combo.domainhostheaders.select_related("domain").all()
        ]

        selected_addresses = (
            random.choices(
                [i[0] for i in all_addressed], weights=[i[1] for i in all_addressed], k=inboundcombochoicegroup.count
            )
            if all_addressed
            else []
        )
        selected_ports = random.choices(ports, k=inboundcombochoicegroup.count) if ports else []
        selected_domain_snis = (
            random.choices(
                [i[0] for i in domain_snis], weights=[i[1] for i in domain_snis], k=inboundcombochoicegroup.count
            )
            if domain_snis
            else []
        )
        selected_domainhostheaders = (
            random.choices(
                [i[0] for i in domainhostheaders], weights=[i[1] for i in domain_snis], k=inboundcombochoicegroup.count
            )
            if domainhostheaders
            else []
        )

        for counter in range(inboundcombochoicegroup.count):
            combo_stat = typing.ComboStat(
                **{
                    "address": py_helpers.access_index_default(selected_addresses, counter, None),
                    "port": py_helpers.access_index_default(selected_ports, counter, None),
                    "sni": py_helpers.access_index_default(selected_domain_snis, counter, None),
                    "domainhostheader": py_helpers.access_index_default(selected_domainhostheaders, counter, None),
                }
            )
            remark_prefix = (
                (subscriptionperiod_obj.plan.connection_rule.inbound_remarks_prefix or "") + f"({combo.pk}-{counter})"
            )
            link_res = django.template.Template(link_template).render(
                context=django.template.Context(
                    {
                        "subscriptionperiod_obj": subscriptionperiod_obj,
                        "combo_stat": combo_stat,
                        "remark_prefix": remark_prefix,
                        "connection_rule": subscriptionperiod_obj.plan.connection_rule,
                    }
                )
            )
            if link_res:
                res_lines.append(link_res)

    sublink_content = "\n".join(res_lines)

    if request.GET.get("base64"):
        sublink_content = base64.b64encode(sublink_content.encode())

    return HttpResponse(sublink_content, content_type="text/plain; charset=utf-8")


async def dynamic_sublink_view(request, sublink_path: str):
    pattern = django.urls.resolvers.RoutePattern(route="change-me/todo/<uuid:subscription_uuid>")
    match = pattern.match(path=sublink_path.rstrip("/"))
    if match is None:
        raise django.urls.Resolver404()
    return await sublink_view(request, **match[2])
