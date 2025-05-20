import enum

from prometheus_client import Counter

from django_prometheus.conf import NAMESPACE

sublink_total = Counter(
    "sublink_total",
    "Total get requests on cache",
    ["variant"],
    namespace=NAMESPACE,
)

class SublinkVariant(enum.StrEnum):
    SIMPLE = "simple"
    SIMPLE_BASE64 = "simple_base64"
