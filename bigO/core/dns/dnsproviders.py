import cloudflare
import pydantic

from .base import BaseDNSProvider


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
        self, base_domain_name: str, name: str, content: str, type: str, comment: str | None = None
    ):
        zones = await self.client.zones.list(name=base_domain_name)
        async for zone in zones:
            zone_id = zone.id
            break
        else:
            raise AssertionError(f"domain {base_domain_name} not found")
        r = await self.client.dns.records.create(
            zone_id=zone.id, name=name, content=content, type="TXT", comment=comment
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
        fdf: int
        fgff: int
