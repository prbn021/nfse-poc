"""Gera PFX autoassinados para os testes (DEC-014). Nenhum dado aqui é real."""

import datetime
from functools import cache

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

CNPJ = "11222333000181"
TITULAR = f"EMPRESA FICTICIA LTDA:{CNPJ}"
# otherName do CNPJ da pessoa jurídica titular nos certificados ICP-Brasil (docs/SPEC.md §6).
OID_CNPJ = x509.ObjectIdentifier("2.16.76.1.3.3")
# Tags DER com que o valor do otherName pode vir.
OCTET_STRING, PRINTABLE_STRING, UTF8_STRING = 0x04, 0x13, 0x0C


@cache
def chave_de_teste() -> rsa.RSAPrivateKey:
    # Gerar a chave é a parte lenta; uma só serve a todos os testes.
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def gerar_certificado(
    *,
    cn: str | None = TITULAR,
    cnpj_no_san: str | None = CNPJ,
    tag_do_san: int = OCTET_STRING,
    inicio: datetime.datetime | None = None,
    dias: int = 365,
) -> x509.Certificate:
    chave = chave_de_teste()
    atributos = [x509.NameAttribute(NameOID.COUNTRY_NAME, "BR")]
    if cn is not None:
        atributos.append(x509.NameAttribute(NameOID.COMMON_NAME, cn))
    nome = x509.Name(atributos)
    inicio = inicio or datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1)
    construtor = (
        x509.CertificateBuilder()
        .subject_name(nome)
        .issuer_name(nome)
        .public_key(chave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(inicio)
        .not_valid_after(inicio + datetime.timedelta(days=dias))
    )
    if cnpj_no_san is not None:
        valor = bytes([tag_do_san, len(cnpj_no_san)]) + cnpj_no_san.encode("ascii")
        construtor = construtor.add_extension(
            x509.SubjectAlternativeName(
                [x509.RFC822Name("contato@exemplo.invalid"), x509.OtherName(OID_CNPJ, valor)]
            ),
            critical=False,
        )
    return construtor.sign(chave, hashes.SHA256())


def gerar_pfx(senha: str, *, com_chave: bool = True, com_certificado: bool = True, **kw) -> bytes:
    cifra = (
        serialization.BestAvailableEncryption(senha.encode("utf-8"))
        if senha
        else serialization.NoEncryption()
    )
    return pkcs12.serialize_key_and_certificates(
        name=b"teste",
        key=chave_de_teste() if com_chave else None,
        cert=gerar_certificado(**kw) if com_certificado else None,
        cas=None,
        encryption_algorithm=cifra,
    )
