import pathlib

from environ import environ

from django.conf import settings

from ._setup import env

# Project's apps stuff...
# ------------------------------------------------------------------------------
# graphql
# ------------------------------------------------------------------------------
# show graphiql panel or not
GRAPHIQL = env.bool("GRAPHIQL", False)

# certificates
# ------------------------------------------------------------------------------
CERTBOT_LOGS_DIR = pathlib.Path(settings.LOGS_DIR) / "certbot"
CERTBOT_LOGS_DIR.mkdir(exist_ok=True)
CERTBOT_CONFIG_DIR = pathlib.Path(settings.MEDIA_ROOT) / "protected" / "certbot"
CERTBOT_CONFIG_DIR.mkdir(exist_ok=True)


# other
TELEGRAM_BOT_TOKEN = env.str("TELEGRAM_BOT_TOKEN")
