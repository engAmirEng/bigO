import abc

from django.db import models


class AbstractProxyUser(models.Model):
    xray_uuid = models.UUIDField(blank=True, unique=True)

    class Meta:
        abstract = True

    @abc.abstractmethod
    def xray_email(self):
        raise NotImplementedError
