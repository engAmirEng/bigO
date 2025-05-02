from . import dnsproviders

__all__ = ["AVAILABLE_DNS_PROVIDERS"]

AVAILABLE_DNS_PROVIDERS = [dnsproviders.CloudflareDNS, dnsproviders.AbrArvanDNS]
