from functools import wraps
from inspect import iscoroutinefunction

from django.http import HttpResponseNotAllowed
from django.utils.log import log_response


def csrf_exempt(view_func):
    """csrf_exempt that supports async view"""
    if iscoroutinefunction(view_func):

        async def _view_wrapper(request, *args, **kwargs):
            return await view_func(request, *args, **kwargs)

    else:

        def _view_wrapper(request, *args, **kwargs):
            return view_func(request, *args, **kwargs)

    _view_wrapper.csrf_exempt = True

    return wraps(view_func)(_view_wrapper)


def require_http_methods(request_method_list):
    """require_http_methods that supports async view"""

    def decorator(func):
        if iscoroutinefunction(func):

            @wraps(func)
            async def inner(request, *args, **kwargs):
                if request.method not in request_method_list:
                    response = HttpResponseNotAllowed(request_method_list)
                    log_response(
                        "Method Not Allowed (%s): %s",
                        request.method,
                        request.path,
                        response=response,
                        request=request,
                    )
                    return response
                return await func(request, *args, **kwargs)

        else:

            @wraps(func)
            def inner(request, *args, **kwargs):
                if request.method not in request_method_list:
                    response = HttpResponseNotAllowed(request_method_list)
                    log_response(
                        "Method Not Allowed (%s): %s",
                        request.method,
                        request.path,
                        response=response,
                        request=request,
                    )
                    return response
                return func(request, *args, **kwargs)

        return inner

    return decorator


def xframe_options_sameorigin(view_func):
    if iscoroutinefunction(view_func):

        @wraps(view_func)
        async def wrapper_view(*args, **kwargs):
            resp = await view_func(*args, **kwargs)
            if resp.get("X-Frame-Options") is None:
                resp["X-Frame-Options"] = "SAMEORIGIN"
            return resp

    else:

        @wraps(view_func)
        def wrapper_view(*args, **kwargs):
            resp = view_func(*args, **kwargs)
            if resp.get("X-Frame-Options") is None:
                resp["X-Frame-Options"] = "SAMEORIGIN"
            return resp

    return wrapper_view
