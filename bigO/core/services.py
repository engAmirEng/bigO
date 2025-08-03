import pathlib
import re
import subprocess
import sys
import uuid
from datetime import datetime, timedelta
from typing import TypedDict
from zoneinfo import ZoneInfo

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from . import models


class CertbotPaths(TypedDict):
    exec_path: pathlib.Path
    logs_dir: pathlib.Path
    config_dir: pathlib.Path
    work_dir: pathlib.Path


def get_certbot_paths() -> CertbotPaths:
    current_python_path = sys.executable
    certbot_path = pathlib.Path(current_python_path).parent / "certbot"
    certbot_logs_dir = settings.CERTBOT_LOGS_DIR
    certbot_config_dir = settings.CERTBOT_CONFIG_DIR
    certbot_work_dir = pathlib.Path("/tmp/certbot")
    return {
        "exec_path": certbot_path,
        "logs_dir": certbot_logs_dir,
        "config_dir": certbot_config_dir,
        "work_dir": certbot_work_dir,
    }


def get_certbot_cert_dir(cert_name) -> pathlib.Path | None:
    certbot_config_dir = get_certbot_paths()["config_dir"]
    certbot_cert_dir = None
    for i in pathlib.Path(certbot_config_dir, "live").iterdir():
        if not i.is_dir() or i.name != cert_name:
            continue
        certbot_cert_dir = i
        break
    return certbot_cert_dir


def certbot_init_new(domains: list[models.Domain]) -> tuple[bool, str]:
    current_python_path = sys.executable
    manage_py_path = str(settings.BASE_DIR / "manage.py")
    certbot_paths = get_certbot_paths()

    for i in domains:
        dns_provider: models.DNSProvider = i.get_dns_provider()
        assert dns_provider
    future_certbotinfo_uuid = uuid.uuid4()
    certificatetask_obj = models.CertificateTask()
    certificatetask_obj.certbot_info_uuid = future_certbotinfo_uuid
    certificatetask_obj.task_type = models.CertificateTask.TaskTypeChoices.ISSUE
    certificatetask_obj.start_certbot_msg = f"init for {','.join([i.name for i in domains])}"
    certificatetask_obj.is_closed = False
    certificatetask_obj.save()
    time_str = timezone.now().astimezone(ZoneInfo("UTC")).strftime("%Y%m%d_%H%M%S")
    cert_name = "_".join([i.name for i in domains]) + f"_{time_str}"

    command_args = [
        certbot_paths["exec_path"],
        "certonly",
        "--manual",
        "--preferred-challenges",
        "dns",
        "--manual-auth-hook",
        f"{current_python_path} {manage_py_path} certbot_auth_hook --init-taskid {certificatetask_obj.id} --certbotinfo-uuid {future_certbotinfo_uuid}",
        "--manual-cleanup-hook",
        f"{current_python_path} {manage_py_path} certbot_cleanup_hook --init-taskid {certificatetask_obj.id} --certbotinfo-uuid {future_certbotinfo_uuid}",
        "--agree-tos",
        # "--manual-public-ip-logging-ok",
        "--non-interactive",
        "--logs-dir",
        certbot_paths["logs_dir"],
        "--config-dir",
        certbot_paths["config_dir"],
        "--work-dir",
        certbot_paths["work_dir"],
        "--cert-name",
        cert_name,
    ]
    for i in domains:
        command_args.extend(
            [
                "-d",
                i.name,
            ]
        )

    if settings.DEBUG:
        command_args.extend(["--dry-run", "--staging"])

    res, err = subprocess.Popen(
        command_args,
        env={},
        stderr=subprocess.PIPE,
        stdout=subprocess.PIPE,
    ).communicate(timeout=800)
    certificatetask_obj.refresh_from_db()
    certbot_res = res.decode("utf-8")
    certbot_err = err.decode("utf-8")

    certificatetask_obj.log("final", certbot_res)
    certificatetask_obj.log("final", certbot_err)
    if "was successful" not in certbot_res and "Successfully" not in certbot_res:
        if "Certificate not yet due for renewal" in certbot_res:
            certificatetask_obj.is_closed = True
            certificatetask_obj.is_success = False
            certificatetask_obj.save()
        if "failed to authenticate" in certbot_res:
            certificatetask_obj.is_closed = True
            certificatetask_obj.is_success = False
            certificatetask_obj.save()
        if "Another instance of Certbot is already running" in certbot_err:
            certificatetask_obj.is_closed = True
            certificatetask_obj.is_success = False
            certificatetask_obj.save()
        return False, certbot_res

    certbot_cert_dir = get_certbot_cert_dir(cert_name)

    if certbot_cert_dir is None:
        certificatetask_obj.log("final", "certbot_cert_dir not found")
        certificatetask_obj.is_closed = True
        certificatetask_obj.is_success = False
        certificatetask_obj.save()
        return False, certbot_res

    private_key_content = certbot_cert_dir.joinpath("privkey.pem").read_bytes()
    cert_content = certbot_cert_dir.joinpath("cert.pem").read_bytes()
    parent_cert_content = certbot_cert_dir.joinpath("chain.pem").read_bytes()

    private_key = serialization.load_pem_private_key(
        private_key_content,
        password=None,
    )
    cert = x509.load_pem_x509_certificate(cert_content)
    parent_cert = x509.load_pem_x509_certificate(parent_cert_content)

    if isinstance(private_key, rsa.RSAPrivateKey):
        algorithm = models.AbstractCryptographicObject.AlgorithmChoices.RSA
    elif isinstance(private_key, ec.EllipticCurvePrivateKey):
        algorithm = models.AbstractCryptographicObject.AlgorithmChoices.ECDSA
    else:
        raise NotImplementedError

    parent_certificate_obj = models.Certificate()
    parent_certificate_obj.algorithm = algorithm
    parent_certificate_obj.content = parent_cert_content.decode()
    parent_certificate_obj.slug = slugify(cert_name + "_chain_cert" + f"_{certificatetask_obj.id}")
    parent_certificate_obj.fingerprint = parent_cert.fingerprint(hashes.SHA256()).hex()
    parent_certificate_obj.valid_from = parent_cert.not_valid_before_utc
    parent_certificate_obj.valid_to = parent_cert.not_valid_after_utc

    privatekey_obj = models.PrivateKey()
    privatekey_obj.algorithm = algorithm
    privatekey_obj.content = private_key_content.decode()
    privatekey_obj.slug = slugify(cert_name + f"_{certificatetask_obj.id}")
    privatekey_obj.key_length = private_key.key_size

    certbotinfo_obj = models.CertbotInfo()
    certbotinfo_obj.uuid = future_certbotinfo_uuid
    certbotinfo_obj.cert_name = cert_name

    certificate_obj = models.Certificate()
    certificate_obj.private_key = privatekey_obj
    certificate_obj.parent_certificate = parent_certificate_obj
    certificate_obj.algorithm = algorithm
    certificate_obj.content = cert_content.decode()
    certificate_obj.slug = cert_name + "_cert" + f"_{certificatetask_obj.id}"
    certificate_obj.fingerprint = cert.fingerprint(hashes.SHA256()).hex()
    certificate_obj.valid_from = cert.not_valid_before_utc
    certificate_obj.valid_to = cert.not_valid_after_utc
    certificate_obj.certbot_info = certbotinfo_obj

    with transaction.atomic(using="main"):
        parent_certificate_obj.save()
        privatekey_obj.save()
        certbotinfo_obj.save()
        certificate_obj.save()
        for i in domains:
            domaincertificate_obj = models.DomainCertificate()
            domaincertificate_obj.domain = i
            domaincertificate_obj.certificate = certificate_obj
            domaincertificate_obj.save()
        certificatetask_obj.is_success = True
        certificatetask_obj.is_closed = True
        certificatetask_obj.save()
    return True, certbot_res


def certbot_init_renew(certbotinfo_obj: models.CertbotInfo) -> tuple[bool, str]:
    cert_name = certbotinfo_obj.cert_name
    certbot_paths = get_certbot_paths()

    domains = [i.domain for i in certbotinfo_obj.certificates.first().certificate_domaincertificates.all()]
    for i in domains:
        dns_provider: models.DNSProvider = i.get_dns_provider()
        assert dns_provider
    certificatetask_obj = models.CertificateTask()
    certificatetask_obj.certbot_info_uuid = certbotinfo_obj.uuid
    certificatetask_obj.task_type = models.CertificateTask.TaskTypeChoices.RENEWAL
    certificatetask_obj.logs = f"init for {','.join([i.name for i in domains])}"
    certificatetask_obj.is_closed = False
    certificatetask_obj.save()

    command_args = [
        certbot_paths["exec_path"],
        "renew",
        "--agree-tos",
        # "--manual-public-ip-logging-ok",
        "--non-interactive",
        "--logs-dir",
        certbot_paths["logs_dir"],
        "--config-dir",
        certbot_paths["config_dir"],
        "--work-dir",
        certbot_paths["work_dir"],
        "--cert-name",
        cert_name,
    ]

    if settings.DEBUG:
        command_args.extend(["--dry-run"])

    res, err = subprocess.Popen(
        command_args,
        env={},
        stderr=subprocess.PIPE,
        stdout=subprocess.PIPE,
    ).communicate(timeout=800)
    certbot_res = res.decode("utf-8")
    certbot_err = err.decode("utf-8")
    just_pars = False

    certificatetask_obj.log("final", "certbot_res: " + certbot_res)
    certificatetask_obj.log("final", "certbot_err: " + certbot_err)
    if "No certificate found with name" in certbot_err:
        certificatetask_obj.log("final", f"is {cert_name} folder deleted?")
        certificatetask_obj.is_success = False
        certificatetask_obj.is_closed = True
        certificatetask_obj.save()
        return False, certbot_err
    if "failed" in certbot_res:
        certificatetask_obj.is_success = False
        certificatetask_obj.is_closed = True
        certificatetask_obj.save()
        return False, certbot_res
    if "Certificate not yet due for renewal" in certbot_res:
        now = timezone.now()
        match = re.search(r"\d{4}-\d{2}-\d{2}", certbot_res)
        if match:
            date_str = match.group(0)
            expires_on_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            if expires_on_date - now.date() < timedelta(days=15):
                certificatetask_obj.is_success = False
                certificatetask_obj.is_closed = True
                certificatetask_obj.save()
                return False, certbot_res
            else:
                # parse the certs
                just_pars = True
        if not just_pars:
            certificatetask_obj.is_success = False
            certificatetask_obj.is_closed = True
            certificatetask_obj.save()
            return False, certbot_res
    if "was successful" not in certbot_res:
        return False, certbot_res

    certbot_cert_dir = get_certbot_cert_dir(cert_name)

    if certbot_cert_dir is None:
        certificatetask_obj.log("final", "certbot_cert_dir not found is deleted?")
        certificatetask_obj.is_closed = True
        certificatetask_obj.is_success = False
        certificatetask_obj.save()
        return False, certbot_res

    private_key_content = certbot_cert_dir.joinpath("privkey.pem").read_bytes()
    cert_content = certbot_cert_dir.joinpath("cert.pem").read_bytes()
    parent_cert_content = certbot_cert_dir.joinpath("chain.pem").read_bytes()

    private_key = serialization.load_pem_private_key(
        private_key_content,
        password=None,
    )
    cert = x509.load_pem_x509_certificate(cert_content)
    parent_cert = x509.load_pem_x509_certificate(parent_cert_content)

    if isinstance(private_key, rsa.RSAPublicKey):
        algorithm = models.AbstractCryptographicObject.AlgorithmChoices.RSA
    elif isinstance(private_key, ec.EllipticCurvePublicKey):
        algorithm = models.AbstractCryptographicObject.AlgorithmChoices.ECDSA
    else:
        raise NotImplementedError

    parent_certificate_obj = models.Certificate.objects.filter(
        fingerprint=parent_cert.fingerprint(hashes.SHA256()).hex()
    ).first()
    if parent_certificate_obj:
        certificatetask_obj.log("final", "found parent cert with fingerprint")
    else:
        certificatetask_obj.log("final", "creating parent cert with new fingerprint")
        parent_certificate_obj = models.Certificate()

    parent_certificate_obj.algorithm = algorithm
    parent_certificate_obj.content = parent_cert_content.decode()
    parent_certificate_obj.slug = slugify(cert_name + "_chain_cert" + f"_{certificatetask_obj.id}")
    parent_certificate_obj.fingerprint = parent_cert.fingerprint(hashes.SHA256()).hex()
    parent_certificate_obj.valid_from = parent_cert.not_valid_before_utc
    parent_certificate_obj.valid_to = parent_cert.not_valid_after_utc

    privatekey_obj = models.PrivateKey.objects.filter(content=private_key_content).first()
    if privatekey_obj:
        certificatetask_obj.log("final", "found private key with same content")
    else:
        certificatetask_obj.log("final", "private key rotated")
        privatekey_obj = models.PrivateKey()
        privatekey_obj.algorithm = algorithm
        privatekey_obj.content = private_key_content.decode()
        privatekey_obj.slug = slugify(cert_name + f"_{certificatetask_obj.id}")
        privatekey_obj.key_length = private_key.key_size

    certificate_obj = models.Certificate.objects.filter(fingerprint=cert.fingerprint(hashes.SHA256()).hex()).first()
    if certificate_obj:
        certificatetask_obj.log("final", "found cert with fingerprint")
    else:
        certificatetask_obj.log("final", "creating cert with new fingerprint")
        certificate_obj = models.Certificate()
        certificate_obj.certbot_info = certbotinfo_obj

    certificate_obj.private_key = privatekey_obj
    certificate_obj.parent_certificate = parent_certificate_obj
    certificate_obj.algorithm = algorithm
    certificate_obj.content = cert_content.decode()
    certificate_obj.slug = slugify(cert_name + "_cert" + f"_{certificatetask_obj.id}")
    certificate_obj.fingerprint = cert.fingerprint(hashes.SHA256()).hex()
    certificate_obj.valid_from = cert.not_valid_before_utc
    certificate_obj.valid_to = cert.not_valid_after_utc

    with transaction.atomic(using="main"):
        parent_certificate_obj.save()
        privatekey_obj.save()
        certificate_obj.save()
        certificatetask_obj.is_success = True
        certificatetask_obj.is_closed = True
        certificatetask_obj.save()
    return True, certbot_res


def get_certbot_current_renew_task(certbotinfo_obj: models.CertbotInfo) -> models.CertificateTask | None:
    certificatetask_obj = models.CertificateTask.objects.filter(
        task_type=models.CertificateTask.TaskTypeChoices.RENEWAL,
        is_closed=False,
        created_at__gt=timezone.now() - timedelta(hours=1),
        certbot_info_uuid=certbotinfo_obj.uuid,
    ).first()
    return certificatetask_obj
