import base64
import uuid

import django.template
import django.urls.resolvers
from django.http import Http404, HttpResponse

from . import models


async def sublink_view(request, subscription_uuid: uuid.UUID):
    # todo save stats
    try:
        subscription_obj: models.Subscription = await models.Subscription.objects.aget(uuid=subscription_uuid)
    except models.Subscription.DoesNotExist:
        raise Http404()
    res_lines = []
    proxy_manager_config = await models.Config.objects.aget()
    sublink_header_content = django.template.Template(proxy_manager_config.sublink_header_template).render(
        context=django.template.Context({"subscription_obj": subscription_obj})
    )
    res_lines.append(sublink_header_content)
    async for i in models.Inbound.objects.filter(is_active=True):
        run_opt = django.template.Template(i.link_template).render(
            context=django.template.Context({"subscription_obj": subscription_obj})
        )
        res_lines.append(run_opt)
    sublink_content = "\n".join(res_lines)

    return HttpResponse(sublink_content, content_type="text/plain; charset=utf-8")

async def dynamic_sublink_view(request, sublink_path: str):
    pattern = django.urls.resolvers.RoutePattern(route="change-me/todo/<uuid:subscription_uuid>")
    match = pattern.match(path=sublink_path.rstrip("/"))
    if match is None:
        raise django.urls.Resolver404()
    return await sublink_view(request, **match[2])
