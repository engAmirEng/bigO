import pathlib
import subprocess
import sys
import uuid

from celery import current_task

from bigO.core import models as core_models
from config.celery_app import app as celery_app
from django.conf import settings
from django.db import transaction

from . import models, services


@celery_app.task()
def issue_certificate_for_domain(domain_id: int):
    current_python_path = sys.executable
    manage_py_path = str(settings.BASE_DIR / "manage.py")
    certbot_path = str(pathlib.Path(current_python_path).parent / "certbot")

    certbot_logs_dir = settings.CERTBOT_LOGS_DIR
    certbot_config_dir = settings.CERTBOT_CONFIG_DIR
    certbot_work_dir = "/tmp/certbot"

    domain_obj = models.Domain.objects.get(id=domain_id)
    certificatetask_obj, future_certbotcert_uuid = services.certbot_init_new(domains=[domain_obj])

    command_args = [
        certbot_path,
        "certonly",
        "--manual",
        "--preferred-challenges",
        "dns",
        "--manual-auth-hook",
        f"{current_python_path} {manage_py_path} certbot_auth_hook --init-taskid {certificatetask_obj.id} --certbotcert-uuid {future_certbotcert_uuid}",
        "--manual-cleanup-hook",
        f"{current_python_path} {manage_py_path} certbot_cleanup_hook --init-taskid {certificatetask_obj.id} --certbotcert-uuid {future_certbotcert_uuid}",
        "--agree-tos",
        # "--manual-public-ip-logging-ok",
        "--non-interactive",
        "--logs-dir",
        certbot_logs_dir,
        "--config-dir",
        certbot_config_dir,
        "--work-dir",
        certbot_work_dir,
        "-d",
        domain_obj.name,
    ]

    if settings.DEBUG:
        command_args.extend(["--staging"])

    res, err = subprocess.Popen(
        command_args,
        env={},
        stderr=subprocess.PIPE,
        stdout=subprocess.PIPE,
    ).communicate(timeout=250)
    certificatetask_obj.refresh_from_db()
    res = res.decode("utf-8")
    certificatetask_obj.log("final", res)
    if not "was successful" in res:
        if "Certificate not yet due for renewal" in res:
            certificatetask_obj.is_closed = True
            certificatetask_obj.is_success = False
            certificatetask_obj.save()
        return False, res
    certbot_cert_names = []
    for i in pathlib.Path(certbot_config_dir).iterdir():
        if not i.is_dir() or i.name:
            continue
        certbotcert_obj = models.CertbotCert.objects.filter(cert_name=i.name).first()
        if not certbot_cert_names



    certbotcert_obj = models.CertbotCert()
    certbotcert_obj.uuid = future_certbotcert_uuid
    certbotcert_obj.certificate
    certbotcert_obj.cert_name

    privatekey_obj = core_models.PrivateKey()
    privatekey_obj

    certificate_obj = core_models.Certificate()
    certificate_obj.private_key = privatekey_obj
    certificate_obj

    domaincertificate_obj = models.DomainCertificate()
    domaincertificate_obj.domain = domain_obj
    domaincertificate_obj.certificate = certificate_obj

    with transaction.atomic():
        privatekey_obj.save()
        certificate_obj.save()
        domaincertificate_obj.save()
    return False, res


@celery_app.task()
def certbot_renew_certificates():
    current_python_path = sys.executable
    manage_py_path = str(settings.BASE_DIR / "manage.py")
    certbot_path = str(pathlib.Path(current_python_path).parent / "certbot")

    certbot_logs_dir = pathlib.Path(settings.LOGS_DIR) / "certbot"
    certbot_logs_dir.mkdir(exist_ok=True)
    certbot_logs_dir = str(certbot_logs_dir)

    certbot_config_dir = pathlib.Path(settings.MEDIA_ROOT) / "protected" / "certbot"
    certbot_config_dir.mkdir(exist_ok=True)
    certbot_config_dir = str(certbot_config_dir)

    certbot_work_dir = "/tmp/certbot"

    command_args = [
        certbot_path,
        "renewal",
        "--agree-tos",
        # "--manual-public-ip-logging-ok",
        "--non-interactive",
        "--logs-dir",
        certbot_logs_dir,
        "--config-dir",
        certbot_config_dir,
        "--work-dir",
        certbot_work_dir,
    ]

    if settings.DEBUG:
        command_args.extend(["--dry-run"])

    res, err = subprocess.Popen(
        command_args,
        env={},
        stderr=subprocess.PIPE,
        stdout=subprocess.PIPE,
    ).communicate(timeout=250)
    res = res.decode("utf-8")
    if not "was successful" in res:
        return False, res

    privatekey_obj = core_models.PrivateKey()
    privatekey_obj

    certificate_obj = core_models.Certificate()
    certificate_obj.private_key = privatekey_obj
    certificate_obj

    domaincertificate_obj = models.DomainCertificate()
    domaincertificate_obj.domain = domain_obj
    domaincertificate_obj.certificate = certificate_obj

    with transaction.atomic():
        privatekey_obj.save()
        certificate_obj.save()
        domaincertificate_obj.save()
    return False, res
