import uuid

from django.db.models import F
from django.db.models.functions import Coalesce
from djmoney.models.fields import MoneyField
from djmoney.models.managers import money_manager, understands_money

from bigO.finance import models as finance_models
from bigO.users.models import User
from bigO.utils.models import TimeStampedModel
from django.db import models, transaction


class SubscriptionPlanInvoiceItem(finance_models.InvoiceItem):
    plan = models.ForeignKey("SubscriptionPlan", on_delete=models.CASCADE, related_name="+")
    plan_args = models.JSONField(null=True, blank=True)
    apply_to = models.ForeignKey(
        "SubscriptionProfile", on_delete=models.CASCADE, related_name="+", null=True, blank=True
    )
    issued_for = models.ForeignKey("AgencyUser", on_delete=models.CASCADE, related_name="+")
    issued_to = models.ForeignKey("AgencyUser", on_delete=models.CASCADE, related_name="+")
    delivered_period = models.ForeignKey(
        "SubscriptionPeriod", on_delete=models.PROTECT, related_name="+", null=True, blank=True
    )

    def __str__(self):
        return f"{self.id}-{self.plan.name}({self.total_price})"

    @property
    def plan_spec_verbose_display(self) -> str:
        plan_provider_cls = self.plan.plan_provider_cls
        if plan_provider_cls.PlanArgsModel and self.plan_args:
            return plan_provider_cls.PlanArgsModel(**self.plan_args).verbose_title()

    def calc_price(self):
        plan_provider = self.plan.plan_provider_cls(
            provider_args=self.plan.plan_provider_args, plan_args=self.plan_args, currency=self.plan.base_currency
        )
        total_price = plan_provider.calc_init_price()
        return total_price

    @transaction.atomic(using="main")
    def deliver(self, actor):
        from .. import services

        can_be_delivered = True
        if can_be_delivered:
            if self.apply_to:
                period = services.create_period(
                    plan=self.plan, plan_args=self.plan_args, subscriptionprofile=self.apply_to, actor=actor
                )
            else:
                profile_uuid = uuid.uuid1()
                title = f"account({profile_uuid.hex[:3]})"
                period = services.create_prfile_with_period(
                    plan=self.plan,
                    plan_args=self.plan_args,
                    agency=self.issued_for.agency,
                    title=title,
                    description="",
                    actor=actor,
                    profile_uuid=profile_uuid,
                    user_profile=self.issued_for.user,
                )
            self.delivered_period = period
            self.save()
        else:
            memberwalletinvoiceitem = MemberWalletInvoiceItem()
            memberwalletinvoiceitem.invoice = self.invoice
            memberwalletinvoiceitem.is_replacement = True
            memberwalletinvoiceitem.total_price = self.total_price
            memberwalletinvoiceitem.created_by = self.created_by
            memberwalletinvoiceitem.agency_user = self.issued_for
            memberwalletinvoiceitem.issued_to = self.issued_to
            memberwalletinvoiceitem.save()
            memberwalletinvoiceitem.deliver(actor=actor)
            self.replacement = memberwalletinvoiceitem
            self.save()


class SubscriptionPeriodInvoiceItem(finance_models.InvoiceItem):
    period = models.ForeignKey("SubscriptionPeriod", on_delete=models.CASCADE, related_name="+")
    issued_to = models.ForeignKey("AgencyUser", on_delete=models.CASCADE, related_name="+")


class MemberWalletInvoiceItem(finance_models.InvoiceItem):
    agency_user = models.ForeignKey("AgencyUser", on_delete=models.CASCADE, related_name="+")
    issued_to = models.ForeignKey("AgencyUser", on_delete=models.CASCADE, related_name="+")
    delivered_credit = models.OneToOneField(
        "MemberCredit", on_delete=models.PROTECT, related_name="+", null=True, blank=True
    )

    def __str__(self):
        return f"{self.id}-{self.agency_user}({self.total_price})"

    @transaction.atomic(using="main")
    def deliver(self, actor):
        membercredit = MemberCredit()
        membercredit.agency_user = self.agency_user
        membercredit.credit = self.total_price
        membercredit.created_by = actor
        if self.is_replacement:
            description = "charge instead of deliver"
        else:
            description = "charge by invoice"
        membercredit.description = description
        membercredit.save()

        self.delivered_credit = membercredit
        self.save()


class SubscriptionPeriodCreditUsage(TimeStampedModel, models.Model):
    period = models.ForeignKey("SubscriptionPeriod", on_delete=models.CASCADE, related_name="+")
    credit = models.OneToOneField("MemberCredit", on_delete=models.CASCADE, related_name="+")


class InvoiceCreditUsage(TimeStampedModel, models.Model):
    invoice = models.ForeignKey("finance.Invoice", on_delete=models.CASCADE, related_name="+")
    credit = models.OneToOneField("MemberCredit", on_delete=models.CASCADE, related_name="+")


class MemberCredit(TimeStampedModel, models.Model):
    class MemberCreditQuerySet(models.QuerySet):
        @understands_money
        def balance(self):
            return self.annotate(
                currency=Coalesce(F("credit_currency"), F("debt_currency"))
            ).order_by().values("agency_user", "currency").annotate(balance=Sum("credit") - Sum("debt"))

    agency_user = models.ForeignKey("AgencyUser", on_delete=models.CASCADE, related_name="+")
    credit = MoneyField(max_digits=14, decimal_places=2, default_currency="USD")
    debt = MoneyField(max_digits=14, decimal_places=2, default_currency="USD")
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    description = models.TextField(blank=True, null=True)

    objects = money_manager(MemberCreditQuerySet.as_manager())


class AgencyPaymentType(TimeStampedModel, models.Model):
    agencyusergroup = models.ForeignKey("AgencyUserGroup", on_delete=models.CASCADE, related_name="+")
    payments = models.ManyToManyField("finance.PaymentProvider", related_name="+")

    def __str__(self):
        return f"{self.id}-{self.agencyusergroup.name}"
