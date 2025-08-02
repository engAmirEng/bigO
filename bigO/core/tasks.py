from config.celery_app import app as celery_app

from . import models, services


@celery_app.task(soft_time_limit=15 * 60, time_limit=16 * 60)
def issue_certificate_for_domain(domain_id: int):
    domain_obj = models.Domain.objects.get(id=domain_id)
    is_success, certbot_res = services.certbot_init_new(domains=[domain_obj])
    return is_success, certbot_res


@celery_app.task(soft_time_limit=15 * 60, time_limit=16 * 60)
def certbot_renew_certificates(certbotinfo_id: int):
    certbotinfo_obj = models.CertbotInfo.objects.get(id=certbotinfo_id)
    is_success, certbot_res = services.certbot_init_renew(certbotinfo_obj=certbotinfo_obj)
    return is_success, certbot_res
