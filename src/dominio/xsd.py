"""Namespace e versão do leiaute da NFS-e e validação offline contra o XSD oficial (T-043).

Comuns à DPS, à NFS-e e aos eventos; saíram de `src/dps.py`.
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree

NS = "http://www.sped.fazenda.gov.br/nfse"
VERSAO = "1.01"  # confira a versão vigente na documentação oficial


def validar_xml(xml: bytes, xsd_path: Path) -> list[str]:
    """Valida contra o XSD oficial. Retorna lista de erros (vazia = válido)."""
    schema = etree.XMLSchema(etree.parse(str(xsd_path)))
    doc = etree.fromstring(xml)
    if schema.validate(doc):
        return []
    return [f"linha {e.line}: {e.message}" for e in schema.error_log]
