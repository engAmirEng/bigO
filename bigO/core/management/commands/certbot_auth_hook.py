import os
import time
import uuid

import dns.resolver
from asgiref.sync import async_to_sync

from django.core.management.base import BaseCommand
from django.utils import timezone

from ... import dns as dns_prs, models, services


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
        certificatetask.log("auth_hook", f"auth_hook: init for {certbot_domain_name}")
        if certificatetask.is_closed:
            certificatetask.log("auth_hook", f"{certificatetask.id=} is closed.")
            raise AssertionError
        try:
            self.fn(certificatetask=certificatetask, certbot_domain_name=certbot_domain_name)
        except Exception as e:
            certificatetask.log("auth_hook", f"auth_hook: error:{str(e)}")
            raise e

    def fn(self, certificatetask, certbot_domain_name):
        sleep_second_for_txt_record = 20
        max_sleep_second_for_txt_record = 100

        certbot_validation = os.environ["CERTBOT_VALIDATION"]
        # os.environ["CERTBOT_TOKEN"]  # HTTP-01 only
        os.environ["CERTBOT_REMAINING_CHALLENGES"]
        os.environ["CERTBOT_ALL_DOMAINS"]
        domain_obj = models.Domain.objects.filter(name=certbot_domain_name).first()
        dns_provider: models.DNSProvider = domain_obj.get_dns_provider()
        assert dns_provider
        domain_root_obj = domain_obj.get_root()
        assert domain_root_obj
        base_domain_name = domain_root_obj.name

        txt_name = f"_acme-challenge.{certbot_domain_name}"
        certificatetask.log("auth_hook", f"auth_hook: doing txt record, {txt_name}: {certbot_validation}")

        provider_record_id = async_to_sync(dns_provider.get_provider().create_record)(
            base_domain_name=base_domain_name,
            name=txt_name,
            content=certbot_validation,
            type=dns_prs.RecordType.TXT,
            comment=f"certbot issue at {timezone.now()}",
        )

        certificatetask.log("auth_hook", f"waiting {sleep_second_for_txt_record} seconds")
        self.stdout.write(
            self.style.SUCCESS(f"txt_created#{provider_record_id}#")
        )  # this line is used by certbot_cleanup_hook to know to delete which record

        t0 = time.perf_counter()
        time.sleep(sleep_second_for_txt_record)
        dns_verified = False
        counter = 0
        while not dns_verified:
            counter += 1
            certificatetask.log(
                "auth_hook", f"auth_hook: {counter}th try to verify the txt record, {txt_name}: {certbot_validation}"
            )
            dns_resolver = dns.resolver.Resolver()
            dns_resolver.nameservers = ["1.1.1.1", "8.8.8.8"]
            try:
                dns_results = dns_resolver.resolve(txt_name, "TXT")
            except dns.resolver.NXDOMAIN:
                pass
            else:
                for dns_result in dns_results:
                    for txt_value in dns_result.strings:
                        if txt_value.decode() == certbot_validation:
                            dns_verified = True
                            certificatetask.log(
                                "auth_hook", f"auth_hook: the txt record verified, {txt_name}: {certbot_validation}"
                            )

            tn = time.perf_counter()
            if (tn - t0) > max_sleep_second_for_txt_record:
                break
            time.sleep(2)
        if not dns_verified:
            certificatetask.log(
                "auth_hook", f"auth_hook: could not verify the txt record, {txt_name}: {certbot_validation}"
            )
