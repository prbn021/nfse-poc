"""Carrega um certificado A1 (PFX/PKCS#12) e expõe certificado e chave privada (T-004).

Caminho e senha chegam como argumentos: não há certificado global (INV-06). A senha não é
guardada, e nem ela nem a chave aparecem em `repr` ou em mensagem de erro (INV-05). Este
módulo não escreve log nem saída.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives.asymmetric.types import PrivateKeyTypes
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

# otherName do Subject Alternative Name com o CNPJ da pessoa jurídica titular, nos
# certificados ICP-Brasil (docs/SPEC.md §6).
OID_CNPJ = x509.ObjectIdentifier("2.16.76.1.3.3")

_CNPJ = re.compile(r"\d{14}")
# Nos certificados de pessoa jurídica o CN costuma terminar em ":<CNPJ>".
_CNPJ_NO_CN = re.compile(r":(\d{14})$")


@dataclass(frozen=True, repr=False)
class Certificado:
    certificado: x509.Certificate
    chave: PrivateKeyTypes
    cadeia: tuple[x509.Certificate, ...]  # demais certificados do PFX (ACs), se houver

    @property
    def titular(self) -> str:
        nomes = self.certificado.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
        return str(nomes[0].value) if nomes else self.certificado.subject.rfc4514_string()

    @property
    def cnpj(self) -> str | None:
        """CNPJ do titular: do otherName do SAN ou, na falta dele, do fim do CN."""
        try:
            san = self.certificado.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        except x509.ExtensionNotFound:
            outros = []
        else:
            outros = san.value.get_values_for_type(x509.OtherName)
        for outro in outros:
            if outro.type_id == OID_CNPJ:
                # O valor vem em DER: um octeto de tipo, um de tamanho e o conteúdo.
                texto = outro.value[2:].decode("ascii", errors="replace")
                return texto if _CNPJ.fullmatch(texto) else None
        no_cn = _CNPJ_NO_CN.search(self.titular)
        return no_cn.group(1) if no_cn else None

    @property
    def valido_de(self) -> datetime:
        return self.certificado.not_valid_before_utc

    @property
    def valido_ate(self) -> datetime:
        return self.certificado.not_valid_after_utc

    def __repr__(self) -> str:
        # Só o que pode ir a um terminal: nada da chave (INV-05).
        return (
            f"Certificado(titular={self.titular!r}, cnpj={self.cnpj!r}, "
            f"valido_ate={self.valido_ate.isoformat()!r})"
        )


def _parece_pfx(dados: bytes) -> bool:
    """Um PFX é uma SEQUENCE DER/BER que começa pelo INTEGER de versão, 3."""
    if len(dados) < 2 or dados[0] != 0x30:
        return False
    tamanho = dados[1]
    inicio = 2 if tamanho <= 0x80 else 2 + (tamanho & 0x7F)
    return dados[inicio : inicio + 3] == b"\x02\x01\x03"


def carregar_certificado(caminho: Path, senha: str) -> Certificado:
    """Abre o PFX em `caminho` com `senha`. Não confere a validade do certificado."""
    if not caminho.is_file():
        raise ValueError(f"certificado não encontrado: {caminho}")
    dados = caminho.read_bytes()
    if not _parece_pfx(dados):
        raise ValueError(f"{caminho.name}: não é um arquivo PFX (PKCS#12)")

    try:
        chave, certificado, cadeia = pkcs12.load_key_and_certificates(dados, senha.encode("utf-8"))
    except ValueError:
        chave = certificado = cadeia = None
        falhou = True
    else:
        falhou = False
    # Levantado fora do `except`, para a exceção da biblioteca não ficar encadeada.
    if falhou:
        raise ValueError(f"{caminho.name}: senha incorreta ou PFX corrompido")
    # Sem a chave, a biblioteca devolve o certificado entre os adicionais, não como principal.
    if chave is None:
        raise ValueError(f"{caminho.name}: PFX sem chave privada")
    if certificado is None:
        raise ValueError(f"{caminho.name}: PFX sem certificado")
    return Certificado(certificado=certificado, chave=chave, cadeia=tuple(cadeia))
