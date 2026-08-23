"""CA interna de Freya (docs/ROADMAP.md Fase 3, punto 4 -- "Gestión de
certificados... sustituyendo la CA de desarrollo de la Fase 0"): emite
certificados de servicio firmados por una CA cuya clave privada vive
cifrada en el propio vault de secrets, nunca en un fichero plano.

Sigue haciendo falta un mínimo en disco -- el arranque en frío es
irresoluble sin él (`infra/certs/ca/ca.crt`, la CA raíz PÚBLICA que todo
contenedor necesita para confiar en la malla antes de poder hablar HTTPS
con nadie, y el primer certificado de cada servicio, generado una vez por
`infra/scripts/gen_dev_ca.sh` para que el propio `secrets` pueda arrancar).
Lo que deja de vivir en disco es la clave PRIVADA de la CA: se importa aquí
una sola vez (`infra/scripts/import_ca.py`) y a partir de ahí toda emisión
o renovación pasa por este módulo, cifrada con la misma envelope encryption
que cualquier otro secreto (`app/domain/vault.py`).
"""

from __future__ import annotations

import datetime
import ipaddress
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from freya_common import NotFound, ServiceClient

from app.domain.crypto import MasterKey
from app.domain.vault import get_secret

# La CA se importa una sola vez con estas mismas keys mediante la API
# genérica de secretos (POST /secrets/freya, overwrite=False -- ver
# infra/scripts/import_ca.py): no hace falta un camino especial de
# importación, es sólo un secreto más protegido por la misma envelope
# encryption que cualquier otro.
_CA_KEY_SECRET = "_internal_ca_key"
_CA_CERT_SECRET = "_internal_ca_cert"
_CERT_VALIDITY_DAYS = 825
_RSA_KEY_SIZE = 2048


async def _load_ca(
    client: ServiceClient, tenant: str, master_key: MasterKey, storage: ServiceClient
) -> tuple[Any, x509.Certificate]:
    try:
        key_secret = await get_secret(
            client,
            tenant,
            master_key,
            storage,
            key=_CA_KEY_SECRET,
            version=None,
            metadata_only=False,
        )
        cert_secret = await get_secret(
            client,
            tenant,
            master_key,
            storage,
            key=_CA_CERT_SECRET,
            version=None,
            metadata_only=False,
        )
    except NotFound as exc:
        raise NotFound(
            "La CA interna todavía no se importó -- corre infra/scripts/import_ca.py"
        ) from exc

    ca_key = serialization.load_pem_private_key(
        key_secret["value"].encode("utf-8"), password=None
    )
    ca_cert = x509.load_pem_x509_certificate(cert_secret["value"].encode("utf-8"))
    return ca_key, ca_cert


async def issue_certificate(
    client: ServiceClient,
    tenant: str,
    master_key: MasterKey,
    storage: ServiceClient,
    *,
    service: str,
) -> dict[str, str]:
    """Emite un certificado de servicio nuevo, firmado por la CA interna.
    Mismos parámetros que emitía infra/scripts/gen_dev_ca.sh: RSA 2048,
    825 días, SAN cubriendo el nombre del contenedor y el nombre corto."""
    ca_key, ca_cert = await _load_ca(client, tenant, master_key, storage)

    service_key = rsa.generate_private_key(
        public_exponent=65537, key_size=_RSA_KEY_SIZE
    )
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"freya-{service}")])
    now = datetime.datetime.now(datetime.UTC)

    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(service_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=_CERT_VALIDITY_DAYS))
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName(f"freya-{service}"),
                    x509.DNSName(service),
                    x509.DNSName("localhost"),
                    x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                ]
            ),
            critical=False,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_encipherment=True,
                content_commitment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage(
                [ExtendedKeyUsageOID.SERVER_AUTH, ExtendedKeyUsageOID.CLIENT_AUTH]
            ),
            critical=False,
        )
    )
    service_cert = builder.sign(ca_key, hashes.SHA256())

    return {
        "tls_key": service_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("utf-8"),
        "tls_crt": service_cert.public_bytes(serialization.Encoding.PEM).decode(
            "utf-8"
        ),
        "ca_crt": ca_cert.public_bytes(serialization.Encoding.PEM).decode("utf-8"),
    }
