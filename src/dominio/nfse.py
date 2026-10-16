"""NFS-e devolvida pela SEFIN e a conferência dela (T-007).

A conferência não aceita nem recusa a nota: a NFS-e já foi gerada quando chega aqui. Ela só
aponta o que não bate (XSD, Ids, ambiente, assinatura), para quem rodou o envio decidir.
A assinatura é conferida por quem chamou (`ConferidorAssinatura`, T-043).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from lxml import etree

from src.dominio.conferencia import ConferidorAssinatura
from src.dominio.erros import MensagemApi
from src.dominio.xsd import NS, validar_xml

_N = {"n": NS}
_HOMOLOGACAO = "2"  # tpAmb da produção restrita (INV-02)


@dataclass(frozen=True)
class NfseEmitida:
    chave: str  # chave de acesso, 50 dígitos
    id_dps: str | None  # None quando a SEFIN devolve só o Id da NFS-e (DEC-045)
    xml: bytes = field(repr=False)
    alertas: tuple[MensagemApi, ...] = ()


@dataclass(frozen=True)
class ResumoDps:
    """O que a substituta de uma nota ME/EPP não pode mudar (E0061/E0063; T-031, T-037)."""

    d_compet: date
    tomador: str | None  # CPF ou CNPJ; None sem tomador identificado
    v_serv: Decimal


def resumo_da_dps(xml: bytes) -> ResumoDps:
    """Competência, tomador e valor do serviço da DPS embutida numa NFS-e.

    Levanta `ValueError` se o XML não for uma NFS-e ou se faltar um desses campos. Não
    confere a nota: isso é de `conferir_nfse`.
    """
    raiz = _ler(xml)
    inf = raiz.find("n:infNFSe/n:DPS/n:infDPS", _N) if raiz is not None else None
    if inf is None:
        raise ValueError("o conteúdo não é uma NFS-e com a DPS embutida")
    texto = inf.findtext("n:dCompet", namespaces=_N)
    try:
        d_compet = date.fromisoformat(texto or "")
    except ValueError:
        d_compet = None
    if d_compet is None:
        raise ValueError("a DPS embutida na NFS-e não tem dCompet válida")
    toma = inf.find("n:toma", _N)
    tomador = None
    if toma is not None:
        tomador = toma.findtext("n:CNPJ", namespaces=_N) or toma.findtext("n:CPF", namespaces=_N)
    try:
        v_serv = Decimal(inf.findtext("n:valores/n:vServPrest/n:vServ", namespaces=_N) or "")
    except InvalidOperation:
        v_serv = None
    if v_serv is None:
        raise ValueError("a DPS embutida na NFS-e não tem vServ válido")
    return ResumoDps(d_compet=d_compet, tomador=tomador, v_serv=v_serv)


def localizar_xsd_nfse(xsd_dir: Path) -> Path | None:
    candidatos = sorted(Path(xsd_dir).glob("NFSe_v*.xsd"))
    return candidatos[-1] if candidatos else None


def _ler(xml: bytes) -> etree._Element | None:
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    try:
        raiz = etree.fromstring(xml, parser)
    except (etree.XMLSyntaxError, ValueError):
        return None
    return raiz if raiz.tag == f"{{{NS}}}NFSe" else None


def conferir_nfse(
    xml: bytes,
    *,
    chave: str,
    id_dps: str | None,
    xsd: Path,
    conferir_assinatura: ConferidorAssinatura,
) -> list[str]:
    """Lista o que não bate na NFS-e devolvida; vazia quando está tudo certo.

    Com `id_dps` None (consulta por chave, T-028), o Id da DPS embutida não é comparado.
    `conferir_assinatura` confere a assinatura do sistema (T-043).
    """
    raiz = _ler(xml)
    if raiz is None:
        return ["o retorno não é uma NFS-e em XML"]

    problemas = []
    erros = validar_xml(xml, xsd)
    if erros:
        extra = f" (e mais {len(erros) - 1})" if len(erros) > 1 else ""
        problemas.append(f"inválida contra {xsd.name}: {erros[0]}{extra}")

    inf = raiz.find("n:infNFSe", _N)
    if inf is None or inf.get("Id") != f"NFS{chave}":
        problemas.append("Id da NFS-e não corresponde à chave de acesso devolvida")

    inf_dps = raiz.find("n:infNFSe/n:DPS/n:infDPS", _N)
    if inf_dps is None and id_dps is None:
        problemas.append("a NFS-e não traz a DPS")
    elif id_dps is not None and (inf_dps is None or inf_dps.get("Id") != id_dps):
        problemas.append("a DPS dentro da NFS-e não é a enviada (Id diferente)")
    elif inf_dps.findtext("n:tpAmb", namespaces=_N) != _HOMOLOGACAO:
        problemas.append("tpAmb da NFS-e não é 2 (produção restrita)")

    try:
        conferir_assinatura(xml)
    except ValueError:
        problemas.append("assinatura da NFS-e não confere com o certificado que ela traz")
    return problemas
