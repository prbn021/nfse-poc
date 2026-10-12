"""Eventos de NFS-e (Anexo II v1.01) e a conferência do evento devolvido pela SEFIN (T-028).

Como em src/nfse.py, a conferência não aceita nem recusa o evento: ele já foi registrado
quando chega aqui. Ela só aponta o que não bate, para quem rodou a consulta decidir.
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from src.assinatura import conferir_assinatura_do_sistema
from src.dps import NS, validar_xml

_N = {"n": NS}
_HOMOLOGACAO = "2"  # tpAmb da produção restrita (INV-02)


def localizar_xsd_evento(xsd_dir: Path) -> Path | None:
    candidatos = sorted(Path(xsd_dir).glob("evento_v*.xsd"))
    return candidatos[-1] if candidatos else None


def _ler(xml: bytes) -> etree._Element | None:
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    try:
        raiz = etree.fromstring(xml, parser)
    except (etree.XMLSyntaxError, ValueError):
        return None
    return raiz if raiz.tag == f"{{{NS}}}evento" else None


def conferir_evento(xml: bytes, *, chave: str, tipo: str, xsd: Path) -> list[str]:
    """Lista o que não bate no evento consultado; vazia quando está tudo certo.

    `tipo` é o código do evento pedido, 6 dígitos (ex.: "101101", cancelamento): o grupo
    específico do pedido de registro se chama `e<tipo>`.
    """
    raiz = _ler(xml)
    if raiz is None:
        return ["o retorno não é um evento em XML"]

    problemas = []
    erros = validar_xml(xml, xsd)
    if erros:
        extra = f" (e mais {len(erros) - 1})" if len(erros) > 1 else ""
        problemas.append(f"inválido contra {xsd.name}: {erros[0]}{extra}")

    pedido = raiz.find("n:infEvento/n:pedRegEvento/n:infPedReg", _N)
    if pedido is None or pedido.findtext("n:chNFSe", namespaces=_N) != chave:
        problemas.append("o evento não é da NFS-e consultada (chNFSe diferente)")
    if pedido is None or pedido.find(f"n:e{tipo}", _N) is None:
        problemas.append(f"o evento não é do tipo pedido ({tipo})")
    elif pedido.findtext("n:tpAmb", namespaces=_N) != _HOMOLOGACAO:
        problemas.append("tpAmb do evento não é 2 (produção restrita)")

    try:
        conferir_assinatura_do_sistema(xml)
    except ValueError:
        problemas.append("assinatura do evento não confere com o certificado que ele traz")
    return problemas
