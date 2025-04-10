import uuid
from datetime import timedelta

from django.utils import timezone

from . import models


def certbot_init_new(domains: list[models.Domain]):
    for i in domains:
        dns_provider: models.DNSProvider = i.get_dns_provider()
        assert dns_provider
    future_certbotcert_uuid = uuid.uuid4()
    certificatetask_obj = models.CertificateTask()
    certificatetask_obj.is_closed = False
    certificatetask_obj.certbot_cert_uuid = future_certbotcert_uuid
    certificatetask_obj.task_type = models.CertificateTask.TaskTypeChoices.ISSUE
    certificatetask_obj.start_certbot_msg = f"init for {','.join([i.name for i in domains])}"
    certificatetask_obj.save()
    return certificatetask_obj, future_certbotcert_uuid


def certbot_init_renew(certbotcert_obj: models.CertbotCert):
    certificatetask_obj = models.CertificateTask.objects.filter(
        task_type=models.CertificateTask.TaskTypeChoices.RENEWAL,
        is_closed=False,
        created_at__gt=timezone.now() - timedelta(hours=1),
        certbot_cert_uuid=certbotcert_obj.uuid,
    ).first()
    if certificatetask_obj:
        return certificatetask_obj
    domain_names = [i.domain.name for i in certbotcert_obj.certificate.certificate_domaincertificates.all()]
    certificatetask_obj = models.CertificateTask()
    certificatetask_obj.certbot_cert_uuid = certbotcert_obj.uuid
    certificatetask_obj.task_type = models.CertificateTask.TaskTypeChoices.RENEWAL
    certificatetask_obj.logs = f"init for {','.join(domain_names)}"
    certificatetask_obj.is_closed = False
    certificatetask_obj.save()
    return certificatetask_obj
