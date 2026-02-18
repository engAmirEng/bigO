import base64
import logging
import random
import re
import uuid

import django.template
import django.urls.resolvers
from django.http import Http404, HttpResponse
from django.template.defaultfilters import floatformat
from django.utils import timezone

from ..utils.templatetags.filesize import convert_SI
from . import metrics, models, services, typing

logger = logging.getLogger(__name__)


async def sublink_view(request, subscription_uuid: uuid.UUID):
    user_agent: str | None = request.headers.get("user_agent")
    is_test = request.GET.get("testing")
    style_type = request.GET.get("style_type")
    try:
        subscriptionprofile_obj = await models.SubscriptionProfile.objects.select_related("initial_agency").aget(
            uuid=subscription_uuid
        )
    except models.SubscriptionProfile.DoesNotExist:
        metrics.sublink_request_total_counter.add(
            1,
            attributes={"user_agent": user_agent, "invalid_secret": subscription_uuid.hex, "status": "not_found"},
        )
        raise Http404()
    subscriptionperiod_obj = (
        await subscriptionprofile_obj.periods.filter(selected_as_current=True)
        .select_related("plan__connection_rule__client_json_template")
        .ann_expires_at()
        .ann_up_bytes_remained()
        .ann_dl_bytes_remained()
        .ann_total_limit_bytes()
        .afirst()
    )
    if subscriptionperiod_obj is None:
        metrics.sublink_request_total_counter.add(
            1,
            attributes={
                "profile_id": subscriptionprofile_obj.id,
                "user_agent": user_agent,
                "status": "no_active_period",
            },
        )
        return "todo"
    if not is_test:
        subscriptionperiod_obj.last_sublink_at = timezone.now()
        await subscriptionperiod_obj.asave()
    r_headers = {}
    short_title = f"⚡️{subscriptionprofile_obj.title}"
    r_headers["profile-title"] = "base64:" + base64.b64encode(short_title.encode("utf-8")).decode()
    r_headers["profile-update-interval"] = "1"
    r_headers["subscription-userinfo"] = (
        f"upload={convert_SI(subscriptionperiod_obj.current_upload_bytes)}; "
        f"download={convert_SI(subscriptionperiod_obj.current_download_bytes)}; "
        f"total={convert_SI(subscriptionperiod_obj.total_limit_bytes)}; "
        f"expire={floatformat(subscriptionperiod_obj.expires_at.timestamp, '0')}"
    )
    is_json_available = (
        subscriptionperiod_obj.plan.connection_rule.client_json_template
        and subscriptionperiod_obj.plan.connection_rule.inbound_choose_rule
        and typing.InboundChooseRuleSchema(
            **subscriptionperiod_obj.plan.connection_rule.inbound_choose_rule
        ).prefer_json_conf
    )
    agent_os_family = random.choices(["win", "android", "ios"], weights=[2, 4, 2], k=1)[0]
    if agent_os_family == "win":
        fp_list = [
            ("chrome", 5),
            ("firefox", 2),
            ("edge", 2),
        ]
    elif agent_os_family == "android":
        fp_list = [
            ("chrome", 5),
            ("firefox", 2),
            ("android", 2),
        ]
    elif agent_os_family == "ios":
        fp_list = [
            ("chrome", 6),
            ("safari", 4),
            ("firefox", 1),
        ]
    else:
        raise NotImplementedError
    if not style_type:
        if not is_json_available:
            style_type = "url"
        elif "happ" in user_agent.lower():
            style_type = "json"
        else:
            style_type = "url"
    if style_type == "url":
        res_lines = []
        sublink_header_content = django.template.Template(
            subscriptionprofile_obj.initial_agency.sublink_header_template
        ).render(context=django.template.Context({"subscriptionperiod_obj": subscriptionperiod_obj}))
        res_lines.append(sublink_header_content)
        proxies = await services.get_profile_proxies(subscriptionperiod_obj=subscriptionperiod_obj)
        res_lines.extend(proxies)

        sublink_content = "\n".join(res_lines)

        if request.GET.get("base64"):
            sublink_content = base64.b64encode(sublink_content.encode())
    elif style_type == "json":
        client_json_template_snippet = subscriptionperiod_obj.plan.connection_rule.client_json_template
        if client_json_template_snippet is None:
            return "todo"
        client_json_template = client_json_template_snippet.template

        profile_json_proxies = await services.get_profile_json_proxies(
            subscriptionperiod_obj=subscriptionperiod_obj, fp_list=fp_list
        )
        reses = []
        if not profile_json_proxies:
            return "todo"
        for profile_json_proxy in profile_json_proxies:
            ctx = {
                "outbounds": profile_json_proxy["outbounds"],
                "balancer": profile_json_proxy["balancer"],
                "remark": profile_json_proxy["remark"],
            }
            res = django.template.Template(client_json_template).render(django.template.Context(ctx))
            reses.append(res)
        sublink_content = "[\n" + ",\n".join(reses) + "\n]"
    else:
        raise NotImplementedError

    metrics.sublink_request_total_counter.add(
        1,
        attributes={
            "connection_rule_id": str(subscriptionperiod_obj.plan.connection_rule_id),
            "profile_id": subscriptionprofile_obj.id,
            "user_agent": user_agent,
            "status": "ok",
        },
    )

    return HttpResponse(sublink_content, headers=r_headers)
