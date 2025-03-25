from asgiref.sync import sync_to_async

from django.http import HttpResponse


async def nginx_flower_auth_request(request):
    is_authenticated = await sync_to_async(lambda: request.user.is_authenticated)()
    if not is_authenticated:
        return HttpResponse(status=401)
    if not request.user.is_superuser:
        return HttpResponse(status=403)
    return HttpResponse(status=200)

async def tmp_rz1(request):
    import django.shortcuts
    import random
    from functools import partial
    from django.utils import timezone
    from zoneinfo import ZoneInfo
    return django.shortcuts.render(
        request, "core/tmp_rz1.html", {
            "random_int": partial(random.randint, 1, 100),
            "last_update_at": timezone.localtime(timezone=ZoneInfo("Asia/Tehran"))
        }
    )
