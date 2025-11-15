import uuid
from datetime import timedelta

from bigO.finance import models as finance_models
from django.db.models import Exists, OuterRef, Q, QuerySet, Subquery
from django.utils import timezone

from ...users.models import User
from .. import models


def get_user_available_plans(*, user, agency):
    qs1 = models.AgencyPlanRestriction.objects.filter(agency=agency).ann_remained_count().filter(remained_count__gt=0)
    qs2 = models.AgencyUserGroup.objects.filter(agency=agency, users=user)
    subscriptionplan_qs = (
        models.SubscriptionPlan.objects.filter(
            is_active=True,
            connection_rule__in=qs1.values("connection_rule"),
            agency=agency,
            allowed_agencyusergroups__id__in=qs2.values("id"),
        )
        .ann_remained_count()
        .filter(remained_count__gt=0)
    )
    return subscriptionplan_qs


def get_user_available_paymentproviders(*, user, agency):
    qs1 = models.AgencyUserGroup.objects.filter(agency=agency, users=user)
    qs_2 = models.AgencyPaymentType.objects.filter(
        agencyusergroups__id__in=qs1.values("id"),
        payments__id=OuterRef("id"),
    )
    paymentprovider_qs = finance_models.PaymentProvider.objects.filter(Q(is_active=True), Exists(qs_2))
    return paymentprovider_qs


def get_agent_available_plans(*, agency) -> QuerySet[models.SubscriptionPlan]:
    qs1 = models.AgencyPlanRestriction.objects.filter(agency=agency).ann_remained_count().filter(remained_count__gt=0)
    subscriptionplan_qs = (
        models.SubscriptionPlan.objects.filter(
            is_active=True,
            connection_rule__in=qs1.values("connection_rule"),
            agency=agency,
        )
        .ann_remained_count()
        .filter(remained_count__gt=0)
    )
    return subscriptionplan_qs


def member_create_bill(
    plan: models.SubscriptionPlan,
    plan_args: dict,
    agency_user: models.AgencyUser,
    profile: models.SubscriptionProfile | None,
    actor: User,
):
    plan_provider = plan.plan_provider_cls(
        provider_args=plan.plan_provider_args, plan_args=plan_args, currency=plan.base_currency
    )
    total_price = plan_provider.calc_init_price()
    now = timezone.now()

    invoice_obj = finance_models.Invoice()
    invoice_obj.uuid = uuid.uuid4()
    invoice_obj.total_price = total_price
    invoice_obj.due_date = now + timedelta(days=1)
    invoice_obj.status = finance_models.Invoice.StatusChoices.ISSUED

    subscriptionplaninvoiceitem_obj = models.SubscriptionPlanInvoiceItem()
    subscriptionplaninvoiceitem_obj.created_by = actor
    subscriptionplaninvoiceitem_obj.total_price = total_price
    subscriptionplaninvoiceitem_obj.invoice = invoice_obj
    subscriptionplaninvoiceitem_obj.plan = plan
    subscriptionplaninvoiceitem_obj.plan_args = plan_args
    subscriptionplaninvoiceitem_obj.apply_to = profile
    subscriptionplaninvoiceitem_obj.issued_for = agency_user
    subscriptionplaninvoiceitem_obj.issued_to = agency_user

    invoice_obj.save()
    subscriptionplaninvoiceitem_obj.save()

    return invoice_obj
