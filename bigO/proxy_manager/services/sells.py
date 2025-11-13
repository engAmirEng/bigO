from django.db.models import OuterRef, QuerySet, Subquery

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
