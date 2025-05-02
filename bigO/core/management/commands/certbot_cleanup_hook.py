import os
import re
import uuid

from asgiref.sync import async_to_sync

from django.core.management.base import BaseCommand

from ... import models, services


class Command(BaseCommand):
    help = "this gets called by certbot"

    def add_arguments(self, parser):
        parser.add_argument("--init-taskid", type=int)
        parser.add_argument("--certbotinfo-uuid", type=uuid.UUID)

    def handle(self, *args, **options):
        initial_task_id = options["init_taskid"]
        certbotinfo_uuid = options["certbotinfo_uuid"]
        certbotinfo_obj = models.CertbotInfo.objects.filter(uuid=certbotinfo_uuid).first()
        is_renew = False
        if certbotinfo_obj:
            is_renew = True
        if not is_renew:
            certificatetask = models.CertificateTask.objects.get(id=initial_task_id)
        else:
            certificatetask = services.get_certbot_current_renew_task(certbotinfo_obj=certbotinfo_obj)
            if certificatetask is None:
                raise Exception("no running certbot renewal task found.")
        certbot_domain_name = os.environ["CERTBOT_DOMAIN"]
        certificatetask.log("cleanup_hook", f"cleanup_hook: init for {certbot_domain_name}")
        if certificatetask.is_closed:
            certificatetask.log("cleanup_hook", f"{certificatetask.id=} is closed.")
            raise AssertionError
        try:
            self.fn(certificatetask=certificatetask, certbot_domain_name=certbot_domain_name)
        except Exception as e:
            certificatetask.log("cleanup_hook", f"error:{str(e)}")
            raise e

    def fn(self, certificatetask, certbot_domain_name):
        os.environ["CERTBOT_VALIDATION"]
        # os.environ["CERTBOT_TOKEN"]  # HTTP-01 only
        os.environ["CERTBOT_REMAINING_CHALLENGES"]
        os.environ["CERTBOT_ALL_DOMAINS"]
        certbot_auth_hook_output: str = os.environ["CERTBOT_AUTH_OUTPUT"]
        # domain_obj = certificatetask.certificatetask_domains.first().domain
        domain_obj = models.Domain.objects.filter(name=certbot_domain_name).first()
        dns_provider: models.DNSProvider = domain_obj.get_dns_provider()
        assert dns_provider
        domain_root_obj = domain_obj.get_root()
        assert domain_root_obj
        base_domain_name = domain_root_obj.name
        match = re.search(r"txt_created#(.*?)#", certbot_auth_hook_output)
        if match:
            provider_record_id = match.group(1)
            certificatetask.log("cleanup_hook", f"deleting dns record {provider_record_id=}")
            # txt_record_id = async_to_sync(dns_provider.get_provider().get_record_id)(
            #     base_domain_name=base_domain_name,
            #     name=f"_acme-challenge.{certbot_domain_name}",
            # )
            async_to_sync(dns_provider.get_provider().delete_record)(
                base_domain_name=base_domain_name,
                record_id=provider_record_id,
            )
        else:
            certificatetask.log("cleanup_hook", "no provider_record_id was created by auth_hook")
