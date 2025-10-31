from bigO.finance import models as finance_models
from bigO.utils.models import TimeStampedModel
from django.db import models


class SubscriptionPlanInvoiceItem(finance_models.InvoiceItem):
    plan = models.ForeignKey("SubscriptionPlan", on_delete=models.PROTECT, related_name="+")
    plan_args = models.JSONField(null=True, blank=True)


class AgencyPaymentType(TimeStampedModel, models.Model):
    agencyusergroup = models.ManyToManyField("AgencyUserGroup", related_name="+")
    payments = models.ManyToManyField("finance.PaymentProvider", related_name="+")
