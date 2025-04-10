import os
import time
import uuid

from asgiref.sync import async_to_sync, sync_to_async

from django.core.management.base import BaseCommand
from django.utils import timezone

from ... import models, services


class Command(BaseCommand):
    help = "this gets called by certbot"

    def add_arguments(self, parser):
        parser.add_argument("init-taskid", type=int)
        parser.add_argument("certbotcert-uuid", type=uuid.uuid4)

    def handle(self, *args, **options):
        initial_task_id = options["init-taskid"]
        certbotcert_uuid = options["certbotcert-uuid"]
        certbotcert_obj = models.CertbotCert.objects.filter(uuid=certbotcert_uuid).first()
        is_renew = False
        if certbotcert_obj:
            is_renew = True
        if not is_renew:
            certificatetask = models.CertificateTask.objects.get(id=initial_task_id)
        else:
            certificatetask = services.certbot_init_renew(certbotcert_obj=certbotcert_obj)
        certbot_domain_name = os.environ["CERTBOT_DOMAIN"]
        certificatetask.log("auth_hook", f"auth_hook: init for {certbot_domain_name}")
        if certificatetask.is_closed != False:
            certificatetask.log("auth_hook", f"{certificatetask.id=} is closed.")
            raise AssertionError
        try:
            self.fn(certificatetask=certificatetask, certbot_domain_name=certbot_domain_name)
        except Exception as e:
            certificatetask.log("auth_hook", f"auth_hook: error:{str(e)}")
            raise e

    def fn(self, certificatetask, certbot_domain_name):
        sleep_second_for_txt_record = 30

        certbot_validation = os.environ["CERTBOT_VALIDATION"]
        # os.environ["CERTBOT_TOKEN"]  # HTTP-01 only
        os.environ["CERTBOT_REMAINING_CHALLENGES"]
        os.environ["CERTBOT_ALL_DOMAINS"]
        domain_obj = models.Domain.objects.filter(name=certbot_domain_name)
        dns_provider: models.DNSProvider = domain_obj.get_dns_provider()
        assert dns_provider
        domain_root_obj = domain_obj.get_root()
        assert domain_root_obj
        base_domain_name = domain_root_obj.name

        txt_name = f"_acme-challenge.{certbot_domain_name}"
        certificatetask.log(
            "auth_hook", f"auth_hook: doing txt record, _acme-challenge.{certbot_domain_name}: {certbot_validation}"
        )

        provider_record_id = async_to_sync(dns_provider.get_provider().create_record)(
            base_domain_name=base_domain_name,
            name=txt_name,
            content=certbot_validation,
            type="TXT",
            comment=f"certbot issue at {timezone.now()}",
        )

        certificatetask.log("auth_hook", f"waiting {sleep_second_for_txt_record} seconds")
        self.stdout.write(
            self.style.SUCCESS(f"txt_created#{provider_record_id}#")
        )  # this line is used by certbot_cleanup_hook to know to delete which record

        time.sleep(sleep_second_for_txt_record)
