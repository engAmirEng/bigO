import ipaddress
from typing import Protocol

import pydantic



class ChooseRuleItemsSchema(pydantic.BaseModel):
    key_name: str
    prefix: str = ""
    count: int

class InboundChooseRuleSchema(pydantic.BaseModel):
    name: str
    inbounds: list[ChooseRuleItemsSchema]


class ComboStat(pydantic.BaseModel):
    address: str | ipaddress.IPv6Address | ipaddress.IPv4Address | None
    port: int | None
    sni: str | None
    domainhostheader: str | None


class ProxyUserProtocol(Protocol):
    @property
    def xray_uuid(self):
        ...

    def xray_email(self):
        ...


#
# class VLESSClient(pydantic.BaseModel):
#     id: uuid.uuid5
#     level: int
#     email: pydantic.EmailStr
#     flow: Literal["", "xtls-rprx-vision"]
#
#
# class VLESSInboundConfigurationObject(pydantic.BaseModel):
#     clients: list[VLESSClient]
#
#
# class ProxyProto(StrEnum):
#     VLESS = "vless"
#     TROJAN = "trojan"
#     VMESS = "vmess"
#     SS = "ss"
#     V2RAY = "v2ray"
#     SSR = "ssr"
#     SSH = "ssh"
#     TUIC = "tuic"
#     HYSTERIA = "hysteria"
#
#
# class InboundObject(pydantic.BaseModel):
#     listen: str
#     port: int
#     protocol: ProxyProto
#     settings: VLESSInboundConfigurationObject
#
#     def protocol(self) -> ProxyProto:
#         return self.settings
