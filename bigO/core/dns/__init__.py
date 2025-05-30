from . import dnsproviders
from .base import RecordType

__all__ = ["AVAILABLE_DNS_PROVIDERS", "RecordType"]

AVAILABLE_DNS_PROVIDERS = [dnsproviders.CloudflareDNS, dnsproviders.AbrArvanDNS]
