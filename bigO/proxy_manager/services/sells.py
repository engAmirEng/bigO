from django.db.models import OuterRef, QuerySet, Subquery

from .. import models


def get_user_available_plans(*, user, agency):
    agencyplanspec_qs = (
        models.AgencyPlanSpec.objects.filter(is_active=True, agency=agency)
        .ann_remained_count()
        .filter(remained_count__gt=0)
    )
    agencyusergroupplanspec_qs = (
        models.AgencyUserGroupPlanSpec.objects.filter(
            is_active=True, agencyusergroup__agency=agency, agencyusergroup__user=user
        )
        .ann_remained_count()
        .filter(remained_count__gt=0)
        .annotate(
            parent_agencyplanspec_id=Subquery(agencyplanspec_qs.filter(plan_id=OuterRef("plan_id")).values("id")[:1])
        )
    )
    return agencyusergroupplanspec_qs.filter(parent_agencyplanspec_id__isnull=False)


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
