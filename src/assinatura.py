"""Assinatura XMLDSIG da DPS e do pedido de evento com o certificado A1 do emitente.

DPS na T-005 (DEC-035); pedido de registro de evento na T-029 (DEC-052).

O perfil é o da assinatura que o próprio sistema nacional põe na NFS-e (docs/SPEC.md §6):
rsa-sha256, sha256 e canonicalização exclusiva com comentários, referência ao `Id` do
elemento assinado (`infDPS` ou `infPedReg`). A SEFIN aceitou esse perfil na DPS em
2026-10-12 (§6); no pedido de evento, só o primeiro cancelamento o confirma (T-030).

A `Signature` sai sem prefixo de namespace, porque a recepção recusa prefixos na área de
dados (E1228). Nenhuma mensagem de erro traz chave, conteúdo do certificado ou trecho do
documento (INV-05); erros do signxml são trocados por uma mensagem própria. Sem log nem saída.
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass

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


@dataclass(frozen=True)
class _Documento:
    """O que muda entre os documentos assinados: raiz, elemento referenciado e autor."""

    nome: str  # nas mensagens: "DPS", "pedido de evento"
    raiz: str
    elemento: str
    caminho_cnpj: str  # CNPJ do emitente dentro do elemento assinado
    sem_cnpj: str
    outro_cnpj: str
    ja_assinado: str
    falha: str


_DPS = _Documento(
    nome="DPS",
    raiz="DPS",
    elemento="infDPS",
    caminho_cnpj="n:prest/n:CNPJ",
    sem_cnpj="certificado sem CNPJ: a assinatura deve ser do emitente (E0718)",
    outro_cnpj=(
        "o CNPJ do certificado não é o do prestador: a assinatura deve ser feita com o "
        "certificado do emitente da DPS (E0718)"
    ),
    ja_assinado="DPS já está assinada",
    falha="falha ao assinar a DPS",
)

# Pedido de registro de evento (Anexo II v1.01, T-029). O servidor confere só a base de 8
# dígitos do CNPJ (E0812); aqui vale o CNPJ inteiro, como na DPS (DEC-052).
_PEDIDO_EVENTO = _Documento(
    nome="pedido de evento",
    raiz="pedRegEvento",
    elemento="infPedReg",
    caminho_cnpj="n:CNPJAutor",
    sem_cnpj="certificado sem CNPJ: a assinatura deve ser do autor do pedido (E1991)",
    outro_cnpj=(
        "o CNPJ do certificado não é o do autor do pedido (CNPJAutor): a assinatura deve ser "
        "feita com o certificado do emitente (E1991, E0812)"
    ),
    ja_assinado="pedido de evento já está assinado",
    falha="falha ao assinar o pedido de evento",
)


def _ler(xml: bytes, doc: _Documento) -> etree._Element:
    # Sem entidades nem acesso à rede ao ler o XML.
    parser = etree.XMLParser(resolve_entities=False, no_network=True, remove_blank_text=False)
    try:
        raiz = etree.fromstring(xml, parser)
    except etree.XMLSyntaxError:
        raise ValueError(f"{doc.nome} não é XML bem formado") from None
    if raiz.tag != f"{{{NS}}}{doc.raiz}":
        raise ValueError(f"raiz não é {doc.raiz} no namespace {NS}")
    return raiz


def _assinar(xml: bytes, cert: Certificado, doc: _Documento) -> bytes:
    if not xml.strip():
        raise ValueError(f"{doc.nome} não é XML bem formado")
    raiz = _ler(xml, doc)
    inf = raiz.find(f"n:{doc.elemento}", _N)
    if inf is None:
        raise ValueError(f"{doc.nome} sem {doc.elemento}")
    id_ = inf.get("Id")
    if not id_:
        raise ValueError(f"{doc.elemento} sem Id")
    if raiz.find(f".//{{{_DS}}}Signature") is not None:
        raise ValueError(doc.ja_assinado)

    if cert.cnpj is None:
        raise ValueError(doc.sem_cnpj)
    if cert.cnpj != inf.findtext(doc.caminho_cnpj, namespaces=_N):
        raise ValueError(doc.outro_cnpj)
    if not isinstance(cert.chave, rsa.RSAPrivateKey):
        raise ValueError("a chave do certificado não é RSA; o perfil usa rsa-sha256")

    signer = XMLSigner(signature_algorithm=ASSINATURA, digest_algorithm=DIGEST, c14n_algorithm=C14N)
    signer.namespaces = {None: _DS}
    try:
        assinada = signer.sign(
            raiz, key=cert.chave, cert=[cert.certificado], reference_uri=f"#{id_}"
        )
        saida = etree.tostring(assinada, xml_declaration=True, encoding="UTF-8")
    except Exception:
        falhou = True
    else:
        falhou = False
    # Levantado fora do `except`, para a exceção da biblioteca não ficar encadeada.
    if falhou:
        raise ValueError(doc.falha)
    return saida


def assinar_dps(xml: bytes, cert: Certificado) -> bytes:
    """Assina o `infDPS` e devolve a DPS com a `Signature` depois dele, em UTF-8."""
    if not isinstance(xml, bytes):
        raise TypeError(f"assinar_dps espera bytes, recebido: {type(xml).__name__}")
    return _assinar(xml, cert, _DPS)


def assinar_pedido_evento(xml: bytes, cert: Certificado) -> bytes:
    """Assina o `infPedReg` do pedido de registro de evento, com o mesmo perfil da DPS.

    A `Signature` sai depois do `infPedReg`, em UTF-8 (T-029, DEC-052).
    """
    if not isinstance(xml, bytes):
        raise TypeError(f"assinar_pedido_evento espera bytes, recebido: {type(xml).__name__}")
    return _assinar(xml, cert, _PEDIDO_EVENTO)


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


def conferir_assinatura_do_sistema(xml: bytes) -> None:
    """Confere a assinatura de um documento com o certificado que vem no próprio `KeyInfo`.

    Serve para a NFS-e devolvida pela SEFIN (T-007): mostra que o XML não mudou depois de
    assinado, mas não que o certificado é do sistema nacional, porque não confere a cadeia.
    Levanta `ValueError` se a assinatura faltar ou não conferir.
    """
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    try:
        raiz = etree.fromstring(xml, parser)
        texto = raiz.findtext(
            f"{{{_DS}}}Signature/{{{_DS}}}KeyInfo/{{{_DS}}}X509Data/{{{_DS}}}X509Certificate"
        )
        certificado = x509.load_der_x509_certificate(
            base64.b64decode("".join((texto or "").split()))
        )
    except (etree.LxmlError, ValueError):
        certificado = None
    if certificado is None:
        raise ValueError("documento sem assinatura ou sem certificado no KeyInfo")
    conferir_assinatura(xml, certificado)
