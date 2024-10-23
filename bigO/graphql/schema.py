import graphene
from django.conf import settings
from graphene_django.debug import DjangoDebug

from bigO.users.schema import Mutation as UsersMutation
from bigO.users.schema import Query as UsersQuery


class Query(UsersQuery, graphene.ObjectType):
    if settings.PLUGGABLE_FUNCS.DEBUG_TOOLBAR:
        debug = graphene.Field(DjangoDebug, name="_debug")

    hello = graphene.String(default_value="Hi!")


class Mutation(graphene.ObjectType, UsersMutation):
    pass


schema = graphene.Schema(query=Query, mutation=Mutation)
