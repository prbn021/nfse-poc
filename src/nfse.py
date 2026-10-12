"""NFS-e devolvida pela SEFIN e a conferência dela (T-007).

A conferência não aceita nem recusa a nota: a NFS-e já foi gerada quando chega aqui. Ela só
aponta o que não bate (XSD, Ids, ambiente, assinatura), para quem rodou o envio decidir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from src.assinatura import conferir_assinatura_do_sistema
from src.dps import NS, validar_xml
from src.erros import MensagemApi

_N = {"n": NS}
_HOMOLOGACAO = "2"  # tpAmb da produção restrita (INV-02)


@dataclass(frozen=True)
class NfseEmitida:
    chave: str  # chave de acesso, 50 dígitos
    id_dps: str | None  # None quando a SEFIN devolve só o Id da NFS-e (DEC-045)
    xml: bytes = field(repr=False)
    alertas: tuple[MensagemApi, ...] = ()


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


def conferir_nfse(xml: bytes, *, chave: str, id_dps: str | None, xsd: Path) -> list[str]:
    """Lista o que não bate na NFS-e devolvida; vazia quando está tudo certo.

    Com `id_dps` None (consulta por chave, T-028), o Id da DPS embutida não é comparado.
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
        conferir_assinatura_do_sistema(xml)
    except ValueError:
        problemas.append("assinatura da NFS-e não confere com o certificado que ela traz")
    return problemas
