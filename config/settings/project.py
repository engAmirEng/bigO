import pathlib

from environ import environ

from django.conf import settings

from ._setup import env

# Project's apps stuff...
# ------------------------------------------------------------------------------
CALENDAR_TYPE = "gregorian"

# graphql
# ------------------------------------------------------------------------------
# show graphiql panel or not
GRAPHIQL = env.bool("GRAPHIQL", False)

# certificates
# ------------------------------------------------------------------------------
CERTBOT_LOGS_DIR = pathlib.Path(settings.LOGS_DIR) / "certbot"
CERTBOT_LOGS_DIR.mkdir(exist_ok=True)
CERTBOT_CONFIG_DIR = pathlib.Path(settings.MEDIA_ROOT) / "protected" / "certbot"

# ansible
# ------------------------------------------------------------------------------
ANSIBLE_WORKING_DIR = pathlib.Path(settings.MEDIA_ROOT) / "protected" / "ansible"
