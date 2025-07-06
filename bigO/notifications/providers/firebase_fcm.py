import hashlib
import json
import logging
from decimal import Decimal
from typing import TYPE_CHECKING

import firebase_admin.messaging

from bigO.users.models import User
from django.conf import settings
from django.views.decorators.debug import sensitive_variables

from .base import BaseNotificationProvider, NotificationInput

if TYPE_CHECKING:
    from ..models import NotificationAccount

from django.utils.translation import gettext_lazy

logger = logging.getLogger(__name__)


class FirebaseFCMNotification(BaseNotificationProvider):
    KEY = "firebase_fcm"
    TITLE = gettext_lazy("firebase fcm")
    TYPE = BaseNotificationProvider.Type.FCM

    EXTRAS_INPUT_SCHEMA = {
        "type": "object",
        "properties": {
            # !!!!Attention, do not expose server_config!!!!
            "server_config": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                    },
                    "project_id": {
                        "type": "string",
                    },
                    "private_key_id": {
                        "type": "string",
                    },
                    "private_key": {
                        "type": "string",
                    },
                    "client_email": {
                        "type": "string",
                    },
                    "client_id": {
                        "type": "string",
                    },
                    "auth_uri": {
                        "type": "string",
                    },
                    "token_uri": {
                        "type": "string",
                    },
                    "auth_provider_x509_cert_url": {
                        "type": "string",
                    },
                    "client_x509_cert_url": {
                        "type": "string",
                    },
                    "universe_domain": {
                        "type": "string",
                    },
                },
            },
            "webapp_config": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "apiKey": {
                            "type": "string",
                        },
                        "authDomain": {
                            "type": "string",
                        },
                        "projectId": {
                            "type": "string",
                        },
                        "storageBucket": {
                            "type": "string",
                        },
                        "messagingSenderId": {
                            "type": "string",
                        },
                        "appId": {
                            "type": "string",
                        },
                    },
                },
            },
            "androidapp_config": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "packageName": {
                            "type": "string",
                        },
                        "apiKey": {
                            "type": "string",
                        },
                        "projectNumber": {
                            "type": "string",
                        },
                        "projectId": {
                            "type": "string",
                        },
                        "storageBucket": {
                            "type": "string",
                        },
                        "appId": {
                            "type": "string",
                        },
                    },
                },
            },
        },
    }

    @sensitive_variables("server_config")
    def __init__(self, server_config: dict, *args, **kwargs):
        assert kwargs.get("account", None) is not None
        self.server_config = server_config
        self.server_config["private_key"] = self.server_config["private_key"].replace("\\n", "\n")  # wired bug
        super().__init__(*args, **kwargs)

    @classmethod
    def initialize_from_account(cls, account: "NotificationAccount"):
        return cls(server_config=account.extras["server_config"], account=account)

    def get_app(self):
        server_config_hash = hashlib.sha256(json.dumps(self.server_config).encode()).hexdigest()
        try:
            app = firebase_admin.get_app(server_config_hash)
        except ValueError:
            # app does not exists
            cred = firebase_admin.credentials.Certificate(self.server_config)
            app = firebase_admin.initialize_app(cred, name=server_config_hash)
        return app

    def send(self, to: User, **kwargs) -> (bool, Decimal):
        from ..models import FCM

        user = to
        fcm_qs = FCM.objects.filter(user_device__user=user, account=self.account)
        app = self.get_app()
        title: str = kwargs.pop(NotificationInput.TITLE, None)
        body: str = kwargs.pop(NotificationInput.BODY)
        link: str = kwargs.pop(NotificationInput.LINK, None)
        icon_url: str = kwargs.pop(NotificationInput.ICON_URL, None)
        image_url: str = kwargs.pop(NotificationInput.IMAGE_URL, None)

        if not settings.DEBUG:
            notification_data = {"body": body}
            if title:
                notification_data["title"] = title
            if image_url:
                notification_data["image"] = image_url
            notification = firebase_admin.messaging.Notification(**notification_data)
            webpush = firebase_admin.messaging.WebpushConfig(
                notification=firebase_admin.messaging.WebpushNotification(icon=icon_url),
                fcm_options=firebase_admin.messaging.WebpushFCMOptions(link=link),
            )
            android = firebase_admin.messaging.AndroidConfig(
                notification=firebase_admin.messaging.AndroidNotification(icon=icon_url)
            )
            success_devices = 0
            for i in fcm_qs:
                try:
                    message = firebase_admin.messaging.Message(
                        notification=notification,
                        token=i.token,
                        webpush=webpush,
                        android=android,
                    )
                    response = firebase_admin.messaging.send(message=message, app=app)
                except firebase_admin._messaging_utils.UnregisteredError:
                    logger.warning(f"{str(i)} raised UnregisteredError")
                    # todo revoke it
                    i.save()
                    continue
                success_devices += 1
                logger.warning(response)
            if success_devices > 0:
                cost = self.get_cost()
                return True, cost
            return False, Decimal(0)
        logger.warning("bypass sending actual sms on debug mode")
        return True, Decimal(0)

    def get_cost(self) -> Decimal:
        return Decimal(0)

    @classmethod
    def get_available_send_vars(cls) -> set:
        return {
            NotificationInput.TITLE,
            NotificationInput.BODY,
            NotificationInput.LINK,
            NotificationInput.ICON_URL,
            NotificationInput.IMAGE_URL,
        }
