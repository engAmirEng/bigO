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


class SubscriptionPeriodInvoiceItem(finance_models.InvoiceItem):
    period = models.ForeignKey("SubscriptionPeriod", on_delete=models.CASCADE, related_name="+")
    issued_to = models.ForeignKey("AgencyUser", on_delete=models.CASCADE, related_name="+")


class MemberWalletInvoiceItem(finance_models.InvoiceItem):
    agency_user = models.ForeignKey("AgencyUser", on_delete=models.CASCADE, related_name="+")
    issued_to = models.ForeignKey("AgencyUser", on_delete=models.CASCADE, related_name="+")


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
    agencyusergroup = models.ManyToManyField("AgencyUserGroup", related_name="+")
    payments = models.ManyToManyField("finance.PaymentProvider", related_name="+")
