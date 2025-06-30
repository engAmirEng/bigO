import zoneinfo

from asgiref.sync import iscoroutinefunction, sync_to_async

from django.utils import timezone
from django.utils.decorators import sync_and_async_middleware


@sync_and_async_middleware
def timezone_middleware(get_response):
    # place after AuthenticationMiddleware
    available_timezones = zoneinfo.available_timezones()
    if iscoroutinefunction(get_response):

        async def middleware(request):
            is_authenticated = await sync_to_async(lambda: request.user.is_authenticated)()
            if is_authenticated:
                preferred_timezone = await sync_to_async(lambda: request.user.preferred_timezone)()
                if preferred_timezone and preferred_timezone in available_timezones:
                    timezone.activate(preferred_timezone)
            response = await get_response(request)
            timezone.deactivate()
            return response

    else:

        def middleware(request):
            is_authenticated = request.user.is_authenticated
            if is_authenticated:
                preferred_timezone = request.user.preferred_timezone
                if preferred_timezone and preferred_timezone in available_timezones:
                    timezone.activate(preferred_timezone)
            response = get_response(request)
            timezone.deactivate()
            return response

    return middleware
