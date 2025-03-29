import asyncio
from functools import wraps

import inertia as base_inertia
from asgiref.sync import sync_to_async

from django.contrib import messages
from django.template.loader import render_to_string


class InertiaResponse(base_inertia.InertiaResponse):
    def __init__(self, *args, inertia_layout, **kwargs):
        self.inertia_layout = inertia_layout
        super().__init__(*args, **kwargs)

    def build_first_load(self, data):
        context, template = self.build_first_load_context_and_template(data)

        return render_to_string(
            template,
            {
                "inertia_layout": self.inertia_layout,
                **context,
            },
            self.request,
            using=None,
        )


def render(request, component, *, inertia_layout, props=None, template_data=None):
    return InertiaResponse(
        request=request,
        component=component,
        inertia_layout=inertia_layout,
        props=props or {},
        template_data=template_data or {},
    )


def inertia(component, layout):
    def decorator(func):
        if asyncio.iscoroutinefunction(func):

            @wraps(func)
            async def inner(request, *args, **kwargs):
                props = await func(request, *args, **kwargs)

                # if something other than a dict is returned, the user probably wants to return a specific response
                if not isinstance(props, dict):
                    return props

                return await sync_to_async(render)(request, inertia_layout=layout, component=component, props=props)

        else:

            @wraps(func)
            def inner(request, *args, **kwargs):
                props = func(request, *args, **kwargs)

                # if something other than a dict is returned, the user probably wants to return a specific response
                if not isinstance(props, dict):
                    return props

                return render(request, inertia_layout=layout, component=component, props=props)

        return inner

    return decorator


def prop_messages():
    def decorator(func):
        if asyncio.iscoroutinefunction(func):

            @wraps(func)
            async def inner(request, *args, **kwargs):
                props = await func(request, *args, **kwargs)
                # if something other than a dict is returned, the user probably wants to return a specific response
                if not isinstance(props, dict):
                    return props
                storage = messages.get_messages(request)
                props["messages"] = [
                    {"message": i.message, "level": i.level, "level_tag": i.level_tag} for i in storage
                ]
                return props

        else:

            @wraps(func)
            def inner(request, *args, **kwargs):
                props = func(request, *args, **kwargs)
                # if something other than a dict is returned, the user probably wants to return a specific response
                if not isinstance(props, dict):
                    return props
                storage = messages.get_messages(request)
                props["messages"] = [
                    {"message": i.message, "level": i.level, "level_tag": i.level_tag} for i in storage
                ]
                return props

        return inner

    return decorator
