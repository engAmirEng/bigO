from functools import wraps

import inertia as base_inertia

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


def render(request, component, inertia_layout, props=None, template_data=None):
    return InertiaResponse(request, component, props or {}, template_data or {}, inertia_layout=inertia_layout)


def inertia(component, layout):
    def decorator(func):
        @wraps(func)
        def inner(request, *args, **kwargs):
            props = func(request, *args, **kwargs)

            # if something other than a dict is returned, the user probably wants to return a specific response
            if not isinstance(props, dict):
                return props

            return render(request, inertia_layout=layout, component=component, props=props)

        return inner

    return decorator
