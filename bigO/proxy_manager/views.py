import base64
import uuid

import django.template
import django.urls.resolvers
from django.http import Http404, HttpResponse
from django.utils import timezone

from . import models


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
        .ann_expires_at()
        .ann_up_bytes_remained()
        .ann_dl_bytes_remained()
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
    async for i in models.Inbound.objects.filter(is_active=True, is_template=True):
        run_opt = django.template.Template(i.link_template).render(
            context=django.template.Context({"subscriptionperiod_obj": subscriptionperiod_obj})
        )
        res_lines.append(run_opt)
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
