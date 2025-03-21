import asyncio
import json
from functools import wraps

import inertia as base_inertia
from asgiref.sync import async_to_sync, sync_to_async
from django.http import HttpResponse

from django.template.loader import render_to_string
from inertia.helpers import validate_type, deep_transform_callables
from inertia.http import BaseInertiaResponseMixin, INERTIA_SESSION_CLEAR_HISTORY, InertiaRequest
from inertia.prop_classes import DeferredProp, MergeableProp, IgnoreOnFirstLoadProp
from inertia.settings import settings


class InertiaResponse(BaseInertiaResponseMixin, HttpResponse):
    json_encoder = settings.INERTIA_JSON_ENCODER
    def __init__(self, *args, inertia_layout, page_data, request, component, props=None, template_data=None, headers=None, **kwargs):
        self.inertia_layout = inertia_layout
        self.request = request
        self.component = component
        self.props = props or {}
        self.template_data = template_data or {}
        _headers = headers or {}

        data = json.dumps(page_data, cls=self.json_encoder)

        if self.request.is_inertia():
            _headers = {
                **_headers,
                'Vary': 'X-Inertia',
                'X-Inertia': 'true',
                'Content-Type': 'application/json',
            }
            content = data
        else:
            content = self.build_first_load(data)

        super().__init__(
            content=content,
            headers=_headers,
            *args,
            **kwargs,
        )

    def page_data(self):
        raise NotImplementedError


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
    def build_props(self):
        raise NotImplementedError
    def build_deferred_props(self):
        raise NotImplementedError
    def build_merge_props(self):
        raise NotImplementedError

def build_props(request, component, props):
    _props = {
      **(request.inertia),
      **props,
    }

    for key in list(_props.keys()):
        if request.is_a_partial_render(component):
          if key not in request.partial_keys():
            del _props[key]
        else:
          if isinstance(_props[key], IgnoreOnFirstLoadProp):
            del _props[key]

    return deep_transform_callables(_props)

def build_deferred_props(request, component, props):
    if request.is_a_partial_render(component):
        return None

    _deferred_props = {}
    for key, prop in props.items():
        if isinstance(prop, DeferredProp):
          _deferred_props.setdefault(prop.group, []).append(key)

    return _deferred_props

def build_merge_props(request, props):
    return [
        key
        for key, prop in props.items()
        if (
          isinstance(prop, MergeableProp)
          and prop.should_merge()
          and key not in request.reset_keys()
        )
    ]
async def get_page_data(request, component, props):
    inertia_session_clear_history = await sync_to_async(request.session.pop)(INERTIA_SESSION_CLEAR_HISTORY, False)
    clear_history = validate_type(
        inertia_session_clear_history,
        expected_type=bool,
        name="clear_history"
    )

    _page = {
        'component': component,
        'props': build_props(request=request, component=component, props=props),
        'url': request.get_full_path(),
        'version': settings.INERTIA_VERSION,
        'encryptHistory': request.should_encrypt_history(),
        'clearHistory': clear_history,
    }

    _deferred_props = build_deferred_props(request=request, component=component, props=props)
    if _deferred_props:
        _page['deferredProps'] = _deferred_props

    _merge_props = build_merge_props(request=request, props=props)
    if _merge_props:
        _page['mergeProps'] = _merge_props

    return _page

async def render(request, component, inertia_layout, props=None, template_data=None):
    request = InertiaRequest(request)
    page_data = await get_page_data(request=request, component=component, props=props)
    return InertiaResponse(request=request, component=component, props=props or {}, template_data=template_data or {}, inertia_layout=inertia_layout, page_data=page_data)


def inertia(component, layout):
    def decorator(func):
        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def inner(request, *args, **kwargs):
                props = await func(request, *args, **kwargs)

                # if something other than a dict is returned, the user probably wants to return a specific response
                if not isinstance(props, dict):
                    return props

                return await render(request, inertia_layout=layout, component=component, props=props)
        else:
            @wraps(func)
            def inner(request, *args, **kwargs):
                props = func(request, *args, **kwargs)

                # if something other than a dict is returned, the user probably wants to return a specific response
                if not isinstance(props, dict):
                    return props

                return async_to_sync(render)(request, inertia_layout=layout, component=component, props=props)

        return inner

    return decorator
