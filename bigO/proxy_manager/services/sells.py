import uuid
from datetime import timedelta

from asgiref.sync import async_to_sync
from moneyed import Money

from bigO.finance import models as finance_models
from bigO.finance.payment_providers.providers import ProxyManagerWalletCredit
from bigO.users.models import User
from django.db import transaction
from django.db.models import Exists, F, OuterRef, Q, QuerySet
from django.utils import timezone

from .. import models


def get_user_available_plans(*, user, agency, current_period: models.SubscriptionPeriod | None = None):
    qs1 = models.AgencyPlanRestriction.objects.filter(agency=agency).ann_remained_count().filter(remained_count__gt=0)
    qs2 = models.AgencyUserGroup.objects.filter(agency=agency, users=user)
    subscriptionplan_qs = models.SubscriptionPlan.objects.filter(
        is_active=True,
        connection_rule__in=qs1.values("connection_rule"),
        agency=agency,
        allowed_agencyusergroups__id__in=qs2.values("id"),
    ).ann_remained_count()
    if current_period is None:
        subscriptionplan_qs = subscriptionplan_qs.filter(remained_count__gt=0)

    else:
        subscriptionplan_qs = subscriptionplan_qs.filter(Q(remained_count__gt=0) | Q(id=current_period.plan_id))
    return subscriptionplan_qs


def get_user_available_paymentproviders(*, user, agency):
    wallet_payment_provider = get_wallet_payment_provider(agency=agency)

    qs1 = models.AgencyUserGroup.objects.filter(agency=agency, users=user)
    qs_2 = models.AgencyPaymentType.objects.filter(
        agencyusergroup_id__in=qs1.values("id"),
        payments__id=OuterRef("id"),
    )
    paymentprovider_qs = finance_models.PaymentProvider.objects.filter(
        Q(is_active=True), Q(Exists(qs_2)) | Q(provider_key=ProxyManagerWalletCredit.TYPE_IDENTIFIER)
    )
    return paymentprovider_qs


def get_agent_available_plans(
    *, agency, current_period: models.SubscriptionPeriod | None = None
) -> QuerySet[models.SubscriptionPlan]:
    qs1 = models.AgencyPlanRestriction.objects.filter(agency=agency).ann_remained_count()
    if current_period is None:
        qs1 = qs1.filter(remained_count__gt=0)
    else:
        qs1 = qs1.filter(Q(remained_count__gt=0) | Q(connection_rule_id=current_period.plan.connection_rule_id))
    subscriptionplan_qs = models.SubscriptionPlan.objects.filter(
        is_active=True,
        connection_rule__in=qs1.values("connection_rule"),
        agency=agency,
    ).ann_remained_count()
    if current_period is None:
        subscriptionplan_qs = subscriptionplan_qs.filter(remained_count__gt=0)
    else:
        subscriptionplan_qs = subscriptionplan_qs.filter(Q(remained_count__gt=0) | Q(id=current_period.plan_id))

    return subscriptionplan_qs


def member_create_wallet_credit_bill(
    amount: Money,
    agency_user: models.AgencyUser,
    actor: User,
):
    invoice_obj = finance_models.Invoice()
    invoice_obj.uuid = uuid.uuid4()

    invoice_obj.status = finance_models.Invoice.StatusChoices.DRAFT

    memberwalletinvoiceitem_obj = models.MemberWalletInvoiceItem()
    memberwalletinvoiceitem_obj.created_by = actor
    memberwalletinvoiceitem_obj.invoice = invoice_obj
    memberwalletinvoiceitem_obj.agency_user = agency_user
    memberwalletinvoiceitem_obj.issued_to = agency_user
    memberwalletinvoiceitem_obj.total_price = amount
    invoice_obj.total_price = invoice_obj.calc_price(items=[memberwalletinvoiceitem_obj])

    invoice_obj.save()
    memberwalletinvoiceitem_obj.save()

    return invoice_obj


def member_create_bill(
    plan: models.SubscriptionPlan,
    plan_args: dict,
    agency_user: models.AgencyUser,
    profile: models.SubscriptionProfile | None,
    actor: User,
) -> models.SubscriptionPlanInvoiceItem:
    invoice_obj = finance_models.Invoice()
    invoice_obj.uuid = uuid.uuid4()

    invoice_obj.status = finance_models.Invoice.StatusChoices.DRAFT

    subscriptionplaninvoiceitem_obj = models.SubscriptionPlanInvoiceItem()
    subscriptionplaninvoiceitem_obj.created_by = actor
    subscriptionplaninvoiceitem_obj.invoice = invoice_obj
    subscriptionplaninvoiceitem_obj.plan = plan
    subscriptionplaninvoiceitem_obj.plan_args = plan_args
    subscriptionplaninvoiceitem_obj.apply_to = profile
    subscriptionplaninvoiceitem_obj.issued_for = agency_user
    subscriptionplaninvoiceitem_obj.issued_to = agency_user

    subscriptionplaninvoiceitem_obj.total_price = subscriptionplaninvoiceitem_obj.calc_price()
    invoice_obj.total_price = invoice_obj.calc_price(items=[subscriptionplaninvoiceitem_obj])

    invoice_obj.save()
    subscriptionplaninvoiceitem_obj.save()

    return subscriptionplaninvoiceitem_obj


def member_prepare_checkout(invoice_obj: finance_models.Invoice):
    assert invoice_obj.status in (
        finance_models.Invoice.StatusChoices.DRAFT,
        finance_models.Invoice.StatusChoices.ISSUED,
    )
    now = timezone.now()
    invoice_obj.status = finance_models.Invoice.StatusChoices.ISSUED
    changed = False
    if invoice_obj.due_date is None or invoice_obj.due_date <= now:
        invoice_obj.due_date = now + timedelta(days=1)
        changed = invoice_obj.redo()
    return changed


def create_prfile_with_period(
    *, plan, plan_args, agency, title, description, actor, profile_uuid=None, user_profile=None
):
    subscriptionprofile = models.SubscriptionProfile()
    subscriptionprofile.initial_agency = agency
    subscriptionprofile.title = title
    subscriptionprofile.uuid = profile_uuid or uuid.uuid4()
    subscriptionprofile.xray_uuid = uuid.uuid4()
    subscriptionprofile.description = description
    subscriptionprofile.is_active = True
    if user_profile:
        subscriptionprofile.user = user_profile
    subscriptionperiod = models.SubscriptionPeriod()
    subscriptionperiod.profile = subscriptionprofile
    subscriptionperiod.plan = plan
    if plan.plan_provider_cls.PlanArgsModel:
        subscriptionperiod.plan_args = plan.plan_provider_cls.PlanArgsModel(**plan_args).model_dump()
    else:
        subscriptionperiod.plan_args = None
    subscriptionperiod.selected_as_current = True
    subscriptionevent = models.SubscriptionEvent()
    subscriptionevent.related_agency = agency
    subscriptionevent.agentuser = actor
    subscriptionevent.profile = subscriptionprofile
    subscriptionevent.period = subscriptionperiod
    subscriptionevent.title = "New Profile Created"
    with transaction.atomic(using="main"):
        subscriptionprofile.save()
        subscriptionperiod.save()
        subscriptionevent.save()
        return subscriptionperiod


def create_period(*, plan, plan_args, subscriptionprofile: models.SubscriptionProfile, actor):
    current_period = async_to_sync(subscriptionprofile.get_current_period)()
    current_period.selected_as_current = False

    subscriptionperiod = models.SubscriptionPeriod()
    subscriptionperiod.profile = subscriptionprofile
    subscriptionperiod.plan = plan
    if plan.plan_provider_cls.PlanArgsModel:
        subscriptionperiod.plan_args = plan.plan_provider_cls.PlanArgsModel(**plan_args).model_dump()
    else:
        subscriptionperiod.plan_args = None
    subscriptionperiod.selected_as_current = True
    subscriptionevent = models.SubscriptionEvent()
    subscriptionevent.related_agency = subscriptionprofile.initial_agency
    subscriptionevent.agentuser = actor
    subscriptionevent.profile = subscriptionprofile
    subscriptionevent.period = subscriptionperiod
    subscriptionevent.title = "New Profile Created"
    with transaction.atomic(using="main"):
        current_period.save()
        subscriptionperiod.save()
        subscriptionevent.save()
        return subscriptionperiod


async def get_invoice_agency(invoice):
    subscriptionplaninvoiceitem_obj = (
        await models.SubscriptionPlanInvoiceItem.objects.filter(invoice=invoice)
        .select_related("issued_for__agency")
        .afirst()
    )
    if subscriptionplaninvoiceitem_obj:
        return subscriptionplaninvoiceitem_obj.issued_for.agency
    memberwalletinvoiceitem_obj = (
        await models.MemberWalletInvoiceItem.objects.filter(invoice=invoice)
        .select_related("agency_user__agency")
        .afirst()
    )
    if memberwalletinvoiceitem_obj:
        return memberwalletinvoiceitem_obj.agency_user.agency
    subscriptionperiodinvoiceitem_obj = (
        await models.SubscriptionPeriodInvoiceItem.objects.filter(invoice=invoice)
        .select_related("issued_to__agency")
        .afirst()
    )
    if subscriptionperiodinvoiceitem_obj:
        return subscriptionperiodinvoiceitem_obj.issued_to.agency


def get_wallet_payment_provider(agency) -> finance_models.PaymentProvider | None:
    obj = finance_models.PaymentProvider.objects.filter(provider_key=ProxyManagerWalletCredit.TYPE_IDENTIFIER).first()
    if obj is None:
        obj = finance_models.PaymentProvider()
        obj.name = "proxy_manager_wallet"
        obj.provider_key = ProxyManagerWalletCredit.TYPE_IDENTIFIER
        obj.is_active = True
        obj.save()
    elif not obj.is_active:
        return None
    return obj


@transaction.atomic(using="main")
def pay_payment_with_wallet(
    payment: finance_models.Payment,
    useragency: models.AgencyUser,
    wallet_paymentprovider: finance_models.PaymentProvider,
    actor: User,
):
    wallet_balances = models.MemberCredit.objects.filter(agency_user=useragency).balance(
        currency=payment.amount.currency
    )
    if wallet_balances >= payment.amount:
        credit = models.MemberCredit()
        credit.agency_user = useragency
        credit.debt = payment.amount
        credit.created_by = actor
        credit.description = "use credit for payment"

        paymentcreditusage = models.PaymentCreditUsage()
        paymentcreditusage.payment = payment
        paymentcreditusage.credit = credit

        credit.save()
        paymentcreditusage.save()
        payment.complete(actor=actor)
    else:
        raise ProxyManagerWalletCredit.NotSufficientCredit()
