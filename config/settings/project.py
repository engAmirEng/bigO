from environ import environ

from ._setup import env

# Project's apps stuff...
# ------------------------------------------------------------------------------
# graphql
# ------------------------------------------------------------------------------
# show graphiql panel or not
GRAPHIQL = env.bool("GRAPHIQL", False)

# node_manager
# ------------------------------------------------------------------------------
SUPERVISOR_BASICAUTH = env.tuple("SUPERVISOR_BASICAUTH")
