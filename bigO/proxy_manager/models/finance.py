from djmoney.models.fields import MoneyField

from bigO.finance import models as finance_models
from bigO.users.models import User
from bigO.utils.models import TimeStampedModel
from django.db import models


class SubscriptionPlanInvoiceItem(finance_models.InvoiceItem):
    plan = models.ForeignKey("SubscriptionPlan", on_delete=models.CASCADE, related_name="+")
    plan_args = models.JSONField(null=True, blank=True)
    apply_to = models.ForeignKey(
        "SubscriptionProfile", on_delete=models.CASCADE, related_name="+", null=True, blank=True
    )
    issued_for = models.ForeignKey("AgencyUser", on_delete=models.CASCADE, related_name="+")
    issued_to = models.ForeignKey("AgencyUser", on_delete=models.CASCADE, related_name="+")

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


class SubscriptionPeriodInvoiceItem(finance_models.InvoiceItem):
    period = models.ForeignKey("SubscriptionPeriod", on_delete=models.CASCADE, related_name="+")
    issued_to = models.ForeignKey("AgencyUser", on_delete=models.CASCADE, related_name="+")


class MemberWalletInvoiceItem(finance_models.InvoiceItem):
    agency_user = models.ForeignKey("AgencyUser", on_delete=models.CASCADE, related_name="+")
    issued_to = models.ForeignKey("AgencyUser", on_delete=models.CASCADE, related_name="+")

    def __str__(self):
        return f"{self.id}-{self.agency_user}({self.total_price})"


class MemberCredit(TimeStampedModel, models.Model):
    payed_invoice_item = models.ForeignKey(
        MemberWalletInvoiceItem, on_delete=models.PROTECT, related_name="+", null=True, blank=True
    )
    agency_user = models.ForeignKey("AgencyUser", on_delete=models.CASCADE, related_name="+")
    credit = MoneyField(max_digits=14, decimal_places=2, default_currency="USD")
    debt = MoneyField(max_digits=14, decimal_places=2, default_currency="USD")
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    description = models.TextField(blank=True, null=True)


class AgencyPaymentType(TimeStampedModel, models.Model):
    agencyusergroup = models.ForeignKey("AgencyUserGroup", on_delete=models.CASCADE, related_name="+")
    payments = models.ManyToManyField("finance.PaymentProvider", related_name="+")

    def __str__(self):
        return f"{self.id}-{self.agencyusergroup.name}"
