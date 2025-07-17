from asgiref.sync import sync_to_async

from django.http import HttpResponse


async def nginx_flower_auth_request(request):
    is_authenticated = await sync_to_async(lambda: request.user.is_authenticated)()
    if not is_authenticated:
        return HttpResponse(status=401)
    if not request.user.is_superuser:
        return HttpResponse(status=403)
    return HttpResponse(status=200)
