import aiohttp
import cloudflare
import pydantic

from .base import BaseDNSProvider, RecordType


class CloudflareDNS(BaseDNSProvider):
    TYPE_IDENTIFIER = "cloudflare"

    class ProviderArgsModel(pydantic.BaseModel):
        user_api_token: str

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.client = cloudflare.AsyncCloudflare(api_token=self.args.user_api_token)

    async def verify(self):
        self.args: self.ProviderArgsModel
        try:
            r = await self.client.user.tokens.verify()
        except Exception as e:
            raise e

    async def create_record(
        self,
        base_domain_name: str,
        name: str,
        content: str,
        type: RecordType,
        comment: str | None = None,
        proxied: bool | None = None,
    ):
        zones = await self.client.zones.list(name=base_domain_name)
        async for zone in zones:
            zone_id = zone.id
            break
        else:
            raise AssertionError(f"domain {base_domain_name} not found")
        proxied = proxied if proxied is not None else cloudflare.NOT_GIVEN
        r = await self.client.dns.records.create(
            zone_id=zone_id, name=name, content=content, type=type, comment=comment, proxied=proxied
        )
        if r is not None:
            return r.id

    async def update_record(
        self,
        record_id: str,
        base_domain_name: str,
        name: str,
        content: str,
        type: RecordType,
        comment: str | None = None,
        proxied: bool | None = None,
    ):
        zones = await self.client.zones.list(name=base_domain_name)
        async for zone in zones:
            zone_id = zone.id
            break
        else:
            raise AssertionError(f"domain {base_domain_name} not found")
        proxied = proxied if proxied is not None else cloudflare.NOT_GIVEN
        r = await self.client.dns.records.update(
            dns_record_id=record_id,
            zone_id=zone_id,
            name=name,
            content=content,
            proxied=proxied,
            type=type,
            comment=comment,
        )
        if r is not None:
            return r.id

    async def get_record_id(self, base_domain_name: str, name: str):
        zones = await self.client.zones.list(name=base_domain_name)
        async for zone in zones:
            zone_id = zone.id
            break
        else:
            raise AssertionError(f"domain {base_domain_name} not found")
        r = await self.client.dns.records.list(zone_id=zone_id, name={"exact": name})
        async for record in r:
            return record.id

    async def delete_record(self, base_domain_name: str, record_id: str):
        zones = await self.client.zones.list(name=base_domain_name)
        async for zone in zones:
            zone_id = zone.id
            break
        else:
            raise AssertionError(f"domain {base_domain_name} not found")
        r = await self.client.dns.records.delete(dns_record_id=record_id, zone_id=zone_id)

        # client.dns.records.list()


class AbrArvanDNS(BaseDNSProvider):
    TYPE_IDENTIFIER = "abr_arvan"

    class ProviderArgsModel(pydantic.BaseModel):
        api_key: str
        machine_user_name: str

    BASE_URL = "https://napi.arvancloud.ir/cdn/4.0"

    async def verify(self) -> None:
        url = f"{self.BASE_URL}/domains"
        async with aiohttp.ClientSession(
            headers={"Authorization": self.args.api_key, "Content-type": "application/json"}
        ) as session:
            async with session.get(url) as response:
                if response.status != 200:
                    raise Exception(await response.text())

    async def create_record(
        self,
        base_domain_name: str,
        name: str,
        content: str,
        type: RecordType,
        comment: str | None = None,
        proxied: bool | None = None,
    ) -> str:
        if type == RecordType.TXT:
            value = {"text": content}
        elif type == RecordType.A or type == RecordType.AAAA:
            value = [{"ip": content}]
        elif type == RecordType.CNAME:
            value = {"host": content}
        else:
            raise NotImplementedError
        name = name.removesuffix("." + base_domain_name)
        url = f"{self.BASE_URL}/domains/{base_domain_name}/dns-records"
        data = {"value": value, "type": type.lower(), "name": name, "ttl": 120, "cloud": bool(proxied)}
        async with aiohttp.ClientSession(
            headers={"Authorization": self.args.api_key, "Content-type": "application/json"}
        ) as session:
            async with session.post(url, json=data) as response:
                if response.status != 201:
                    raise Exception(await response.text())
                response_dict = await response.json()
                return response_dict["data"]["id"]

    async def update_record(
        self,
        record_id: str,
        base_domain_name: str,
        name: str,
        content: str,
        type: RecordType,
        comment: str | None = None,
        proxied: bool | None = None,
    ):
        if type == RecordType.TXT:
            value = {"text": content}
        elif type == RecordType.A or type == RecordType.AAAA:
            value = [{"ip": content}]
        elif type == RecordType.CNAME:
            value = {"host": content}
        else:
            raise NotImplementedError
        name = name.removesuffix("." + base_domain_name)
        url = f"{self.BASE_URL}/domains/{base_domain_name}/dns-records/{record_id}"
        data = {"value": value, "type": type.lower(), "name": name, "ttl": 120, "cloud": bool(proxied)}
        async with aiohttp.ClientSession(
            headers={"Authorization": self.args.api_key, "Content-type": "application/json"}
        ) as session:
            async with session.put(url, json=data) as response:
                if response.status != 200:
                    raise Exception(await response.text())
                response_dict = await response.json()
                return response_dict["data"]["id"]

    async def get_record_id(self, base_domain_name: str, name: str):
        name = name.removesuffix("." + base_domain_name)
        url = f"{self.BASE_URL}/domains/{base_domain_name}/dns-records"
        params = {"search": name}
        async with aiohttp.ClientSession(
            headers={"Authorization": self.args.api_key, "Content-type": "application/json"}
        ) as session:
            async with session.get(url, params=params) as response:
                if response.status != 200:
                    raise Exception(await response.text())
                response_dict = await response.json()
                if response_dict["data"]:
                    return response_dict["data"][0]["id"]

    async def delete_record(self, base_domain_name: str, record_id: str):
        url = f"{self.BASE_URL}/domains/{base_domain_name}/dns-records/{record_id}"
        async with aiohttp.ClientSession(
            headers={"Authorization": self.args.api_key, "Content-type": "application/json"}
        ) as session:
            async with session.delete(url) as response:
                if response.status != 200:
                    raise Exception(await response.text())
