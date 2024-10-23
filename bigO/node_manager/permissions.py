import typing

from rest_framework_api_key.permissions import BaseHasAPIKey

from django.http import HttpRequest

from .models import NodeAPIKey


class HasNodeAPIKey(BaseHasAPIKey):
    model = NodeAPIKey

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.api_key: NodeAPIKey | None = None
        self.had_permission: bool | None = None

    def has_permission(self, request: HttpRequest, view: typing.Any) -> bool:
        key = self.get_key(request)
        self.had_permission = False
        if not key:
            return False
        try:
            api_key = self.model.objects.get_from_key(key)
        except self.model.DoesNotExist:
            return False
        self.api_key = api_key
        if api_key.has_expired:
            return False
        self.had_permission = True
        return True
