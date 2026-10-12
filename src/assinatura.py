"""Assinatura XMLDSIG da DPS com o certificado A1 do emitente (T-005, DEC-035).

O perfil é o da assinatura que o próprio sistema nacional põe na NFS-e (docs/SPEC.md §6):
rsa-sha256, sha256 e canonicalização exclusiva com comentários, referência ao `Id` do
`infDPS`. Só a primeira transmissão confirma que a SEFIN o aceita na DPS (T-007).

A `Signature` sai sem prefixo de namespace, porque a recepção recusa prefixos na área de
dados (E1228). Nenhuma mensagem de erro traz chave, conteúdo do certificado ou trecho da
DPS (INV-05); erros do signxml são trocados por uma mensagem própria. Sem log nem saída.
"""

from __future__ import annotations

import logging

from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import rsa
from lxml import etree
from signxml import (
    CanonicalizationMethod,
    DigestAlgorithm,
    SignatureConfiguration,
    SignatureMethod,
    XMLSigner,
    XMLVerifier,
    namespaces,
)
from signxml.exceptions import SignXMLException

from src.certificado import Certificado
from src.dps import NS

# Se a SEFIN recusar a assinatura (E0714), a canonicalização é o primeiro ponto a revisar.
C14N = CanonicalizationMethod.EXCLUSIVE_XML_CANONICALIZATION_1_0_WITH_COMMENTS
ASSINATURA = SignatureMethod.RSA_SHA256
DIGEST = DigestAlgorithm.SHA256

_DS = namespaces.ds
_N = {"n": NS}

# O signxml registra em DEBUG o XML canonicalizado, com CNPJ, CPF do tomador e valores; é o
# único registro de log da versão 5.1.0 (signxml/processor.py).
logging.getLogger("signxml").setLevel(logging.INFO)


def _ler(xml: bytes) -> etree._Element:
    # Sem entidades nem acesso à rede ao ler o XML.
    parser = etree.XMLParser(resolve_entities=False, no_network=True, remove_blank_text=False)
    try:
        raiz = etree.fromstring(xml, parser)
    except etree.XMLSyntaxError:
        raise ValueError("DPS não é XML bem formado") from None
    if raiz.tag != f"{{{NS}}}DPS":
        raise ValueError(f"raiz não é DPS no namespace {NS}")
    return raiz


def assinar_dps(xml: bytes, cert: Certificado) -> bytes:
    """Assina o `infDPS` e devolve a DPS com a `Signature` depois dele, em UTF-8."""
    if not isinstance(xml, bytes):
        raise TypeError(f"assinar_dps espera bytes, recebido: {type(xml).__name__}")
    if not xml.strip():
        raise ValueError("DPS não é XML bem formado")
    raiz = _ler(xml)
    inf = raiz.find("n:infDPS", _N)
    if inf is None:
        raise ValueError("DPS sem infDPS")
    id_dps = inf.get("Id")
    if not id_dps:
        raise ValueError("infDPS sem Id")
    if raiz.find(f".//{{{_DS}}}Signature") is not None:
        raise ValueError("DPS já está assinada")

    cnpj_prestador = inf.findtext("n:prest/n:CNPJ", namespaces=_N)
    if cert.cnpj is None:
        raise ValueError("certificado sem CNPJ: a assinatura deve ser do emitente (E0718)")
    if cert.cnpj != cnpj_prestador:
        raise ValueError(
            "o CNPJ do certificado não é o do prestador: a assinatura deve ser feita com o "
            "certificado do emitente da DPS (E0718)"
        )
    if not isinstance(cert.chave, rsa.RSAPrivateKey):
        raise ValueError("a chave do certificado não é RSA; o perfil usa rsa-sha256")

    signer = XMLSigner(signature_algorithm=ASSINATURA, digest_algorithm=DIGEST, c14n_algorithm=C14N)
    signer.namespaces = {None: _DS}
    try:
        assinada = signer.sign(
            raiz, key=cert.chave, cert=[cert.certificado], reference_uri=f"#{id_dps}"
        )
        saida = etree.tostring(assinada, xml_declaration=True, encoding="UTF-8")
    except Exception:
        falhou = True
    else:
        falhou = False
    # Levantado fora do `except`, para a exceção da biblioteca não ficar encadeada.
    if falhou:
        raise ValueError("falha ao assinar a DPS")
    return saida


def conferir_assinatura(xml: bytes, certificado: x509.Certificate) -> None:
    """Confere a assinatura da DPS com o certificado dado; levanta `ValueError` se falhar.

    Não confere validade nem cadeia do certificado: isso é da SEFIN (E0715, E0716).
    """
    config = SignatureConfiguration(
        location="./",
        signature_methods=frozenset({ASSINATURA}),
        digest_algorithms=frozenset({DIGEST}),
    )
    try:
        XMLVerifier().verify(xml, x509_cert=certificado, expect_config=config)
    except (SignXMLException, ValueError, etree.LxmlError):
        falhou = True
    else:
        falhou = False
    if falhou:
        raise ValueError("assinatura inválida para este certificado")
