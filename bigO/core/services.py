import datetime

from cryptography import x509
from cryptography.hazmat._oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from django.db import transaction

from . import models


def create_asymmetric_rsa(
    name: str,
    valid_after: datetime.datetime,
    valid_before: datetime.datetime,
    parent_public_key_obj: models.PublicKey | None,
    common_name: str,
) -> tuple[models.PrivateKey, models.PublicKey]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "California"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, "San Francisco"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "My CA Organization"),
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ]
    )
    if parent_public_key_obj is None:
        certificate = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(subject)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(valid_after)
            .not_valid_after(valid_before)
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(
                x509.SubjectAlternativeName([x509.DNSName(common_name)]),
                critical=False,
            )
            .sign(private_key=private_key, algorithm=hashes.SHA256())
        )
    else:
        csr = (
            x509.CertificateSigningRequestBuilder()
            .subject_name(subject)
            .sign(private_key=private_key, algorithm=hashes.SHA256())
        )
        parent_certificate = x509.load_pem_x509_certificate(parent_public_key_obj.content.encode("utf-8"))
        parent_private_key = serialization.load_pem_private_key(
            parent_public_key_obj.private_key.content.encode("utf-8"),
            password=None,
        )
        certificate = (
            x509.CertificateBuilder()
            .subject_name(csr.subject)
            .issuer_name(parent_certificate.subject)
            .public_key(csr.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(valid_after)
            .not_valid_after(valid_before)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .sign(private_key=parent_private_key, algorithm=hashes.SHA256())
        )

    private_key_content = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    private_key_fingerprint = hashes.Hash(hashes.SHA256())
    private_key_fingerprint.update(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    private_key_fingerprint = private_key_fingerprint.finalize().hex()

    certificate_content = certificate.public_bytes(serialization.Encoding.PEM)
    privatekey_obj = models.PrivateKey()
    privatekey_obj.algorithm = models.PrivateKey.AlgorithmChoices.RSA
    privatekey_obj.content = private_key_content.decode("utf-8")
    privatekey_obj.fingerprint = private_key_fingerprint
    privatekey_obj.slug = name
    privatekey_obj.key_length = private_key.key_size
    publickey_obj = models.PublicKey()
    publickey_obj.private_key = privatekey_obj
    publickey_obj.slug = f"{privatekey_obj.slug}-public"
    publickey_obj.content = certificate_content.decode("utf-8")
    publickey_obj.fingerprint = certificate.fingerprint(hashes.SHA256())
    publickey_obj.algorithm = models.PrivateKey.AlgorithmChoices.RSA
    publickey_obj.parent_public_key = parent_public_key_obj
    publickey_obj.valid_from = valid_after
    publickey_obj.valid_to = valid_before
    with transaction.atomic():
        privatekey_obj.save()
        publickey_obj.save()
    return privatekey_obj, publickey_obj
