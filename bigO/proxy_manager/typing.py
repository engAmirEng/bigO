import uuid
from enum import StrEnum
from typing import Literal

import pydantic


class VLESSClient(pydantic):
    id: uuid.uuid5
    level: int
    email: pydantic.EmailStr
    flow: Literal["", "xtls-rprx-vision"]


class VLESSInboundConfigurationObject(pydantic):
    clients: list[VLESSClient]


class ProxyProto(StrEnum):
    VLESS = "vless"
    TROJAN = "trojan"
    VMESS = "vmess"
    SS = "ss"
    V2RAY = "v2ray"
    SSR = "ssr"
    SSH = "ssh"
    TUIC = "tuic"
    HYSTERIA = "hysteria"


class InboundObject(pydantic.BaseModel):
    listen: str
    port: int
    protocol: ProxyProto
    settings: VLESSInboundConfigurationObject

    def protocol(self) -> ProxyProto:
        return self.settings
