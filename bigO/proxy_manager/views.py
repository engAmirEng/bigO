import base64
import logging
import uuid

import django.template
import django.urls.resolvers
from django.http import Http404, HttpResponse
from django.utils import timezone

from . import metrics, models, services

logger = logging.getLogger(__name__)


async def sublink_view(request, subscription_uuid: uuid.UUID):
    # todo save stats
    user_agent: str | None = request.headers.get("user_agent")
    is_test = request.GET.get("testing")
    try:
        subscriptionprofile_obj = await models.SubscriptionProfile.objects.select_related("initial_agency").aget(
            uuid=subscription_uuid
        )
    except models.SubscriptionProfile.DoesNotExist:
        metrics.sublink_request_total_counter.add(
            1,
            attributes={"user_agent": user_agent, "invalid_secret": subscription_uuid, "status": "not_found"},
        )
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
    metrics.sublink_request_total_counter.add(
        1,
        attributes={"profile_id": subscriptionprofile_obj.id, "user_agent": user_agent, "status": "ok"},
    )

    return HttpResponse(sublink_content, content_type="text/plain; charset=utf-8")
