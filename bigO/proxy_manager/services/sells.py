from django.db.models import Subquery, OuterRef, QuerySet

from .. import models

def get_user_available_plans(*, user, agency):
    agencyplanspec_qs = models.AgencyPlanSpec.objects.filter(is_active=True, agency=agency).ann_remained_count().filter(remained_count__gt=0)
    agencyusergroupplanspec_qs = models.AgencyUserGroupPlanSpec.objects\
        .filter(is_active=True, agencyusergroup__agency=agency, agencyusergroup__user=user)\
        .ann_remained_count().filter(remained_count__gt=0)\
        .annotate(parent_agencyplanspec_id=Subquery(agencyplanspec_qs.filter(plan_id=OuterRef("plan_id")).values("id")[:1]))
    return agencyusergroupplanspec_qs.filter(parent_agencyplanspec_id__isnull=False)


def get_agent_available_plans(*, agency, user=None) -> QuerySet[models.AgencyUserGroupPlanSpec] | QuerySet[models.AgencyPlanSpec]:
    agencyplanspec_qs = models.AgencyPlanSpec.objects.filter(is_active=True, agency=agency).ann_remained_count().filter(remained_count__gt=0)
    if user:
        agencyusergroupplanspec_qs = models.AgencyUserGroupPlanSpec.objects\
            .filter(is_active=True, agencyusergroup__agency=agency, agencyusergroup__user=user) \
            .ann_remained_count().filter(remained_count__gt=0) \
            .annotate(parent_agencyplanspec_id=Subquery(agencyplanspec_qs.filter(plan_id=OuterRef("plan_id")).values("id")[:1]))
        return agencyusergroupplanspec_qs.filter(parent_agencyplanspec_id__isnull=False)
    return agencyplanspec_qs
