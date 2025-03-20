import pydantic

from bigO.utils.models import MakeInterval
from django.db.models import Case, DateTimeField, F, PositiveBigIntegerField, When
from django.db.models.functions import Cast, Now

from .base import BaseSubscriptionPlanProvider


class TypeSimpleStrict1(BaseSubscriptionPlanProvider):
    TYPE_IDENTIFIER = "type_simple_strict1"

    class ProviderArgsModel(pydantic.BaseModel):
        total_usage_limit_bytes: int
        expiry_seconds: int

    PlanArgsModel = None

    @classmethod
    def get_expires_at_ann_expr(cls):
        a = MakeInterval(Cast("plan__plan_provider_args__expiry_seconds", PositiveBigIntegerField()))
        return Case(
            When(first_usage_at__isnull=False, then=F("first_usage_at") + a),
            default=Now() + a,
            output_field=DateTimeField(),
        )

    @classmethod
    def get_dl_bytes_remained_expr(cls):
        return (
            Cast("plan__plan_provider_args__total_usage_limit_bytes", PositiveBigIntegerField())
            - F("current_download_bytes")
            - F("current_upload_bytes")
        )

    @classmethod
    def get_up_bytes_remained_expr(cls):
        return (
            Cast("plan__plan_provider_args__total_usage_limit_bytes", PositiveBigIntegerField())
            - F("current_download_bytes")
            - F("current_upload_bytes")
        )


class TypeSimpleDynamic1(BaseSubscriptionPlanProvider):
    TYPE_IDENTIFIER = "type_simple_dynamic1"

    ProviderArgsModel = None

    class PlanArgsModel(pydantic.BaseModel):
        total_usage_limit_bytes: int
        expiry_seconds: int

    @classmethod
    def get_expires_at_ann_expr(cls):
        # a = ExpressionWrapper(
        #     Cast('plan_args__expiry_seconds', IntegerField()) * 1_000_000,  # Convert seconds to microseconds
        #     output_field=DurationField()
        # )
        a = MakeInterval(Cast("plan_args__expiry_seconds", PositiveBigIntegerField()))
        return Case(
            When(first_usage_at__isnull=False, then=F("first_usage_at") + a),
            default=Now() + a,
            output_field=DateTimeField(),
        )

    @classmethod
    def get_dl_bytes_remained_expr(cls):
        return (
            Cast("plan_args__total_usage_limit_bytes", PositiveBigIntegerField())
            - F("current_download_bytes")
            - F("current_upload_bytes")
        )

    @classmethod
    def get_up_bytes_remained_expr(cls):
        return (
            Cast("plan_args__total_usage_limit_bytes", PositiveBigIntegerField())
            - F("current_download_bytes")
            - F("current_upload_bytes")
        )
