from environ import environ

from ._setup import env

# Project's apps stuff...
# ------------------------------------------------------------------------------
# graphql
# ------------------------------------------------------------------------------
# show graphiql panel or not
GRAPHIQL = env.bool("GRAPHIQL", False)

# other
TELEGRAM_BOT_TOKEN = env.str("TELEGRAM_BOT_TOKEN")
