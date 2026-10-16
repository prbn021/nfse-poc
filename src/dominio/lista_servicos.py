"""Lista de serviços nacional (Anexo B, aba LISTA.SERV.NAC.), lida do xlsx oficial (T-026).

O xlsx é um zip de XMLs, lidos com lxml sem entidades nem rede. Usada para varrer os códigos
de tributação nacional na consulta de parâmetros municipais do ADN (DEC-042).
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

from lxml import etree

_M = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_ABA = "LISTA.SERV.NAC."
_CELULA = re.compile(r"([A-Z]+)(\d+)")
_CODIGO = re.compile(r"\d{1,6}")
_PARSER = etree.XMLParser(resolve_entities=False, no_network=True)


def _xml(dados: bytes):
    return etree.fromstring(dados, _PARSER)


def localizar_anexo_b(pasta: Path) -> Path | None:
    candidatos = sorted(Path(pasta).glob("anexo_b-*.xlsx"))
    return candidatos[-1] if candidatos else None


def _textos(zip_: zipfile.ZipFile) -> list[str]:
    try:
        raiz = _xml(zip_.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    return ["".join(t.text or "" for t in si.iter(f"{_M}t")) for si in raiz.iter(f"{_M}si")]


def _caminho_da_aba(zip_: zipfile.ZipFile, nome: str) -> str:
    livro = _xml(zip_.read("xl/workbook.xml"))
    relacoes = _xml(zip_.read("xl/_rels/workbook.xml.rels"))
    alvos = {r.get("Id"): r.get("Target") for r in relacoes}
    for aba in livro.iter(f"{_M}sheet"):
        if aba.get("name") == nome:
            alvo = alvos[aba.get(f"{_R}id")].lstrip("/")
            return alvo if alvo.startswith("xl/") else f"xl/{alvo}"
    raise ValueError(f"aba {nome!r} não encontrada no Anexo B")


def _valor(celula, textos: list[str]) -> str:
    if celula.get("t") == "inlineStr":
        return "".join(t.text or "" for t in celula.iter(f"{_M}t"))
    valor = celula.find(f"{_M}v")
    if valor is None or valor.text is None:
        return ""
    return textos[int(valor.text)] if celula.get("t") == "s" else valor.text


def servicos_nacionais(xlsx: Path) -> list[tuple[str, str]]:
    """(código de 6 dígitos, descrição) de cada desdobro nacional, na ordem da planilha.

    Só as linhas com código na coluna A; as de item e de subitem não têm. A planilha guarda o
    código como número, sem o zero à esquerda (`10101` é o `010101`).
    """
    with zipfile.ZipFile(xlsx) as zip_:
        textos = _textos(zip_)
        aba = _xml(zip_.read(_caminho_da_aba(zip_, _ABA)))
    servicos, vistos = [], set()
    for linha in aba.iter(f"{_M}row"):
        colunas = {}
        for celula in linha.findall(f"{_M}c"):
            achado = _CELULA.fullmatch(celula.get("r", ""))
            if achado:
                colunas[achado.group(1)] = _valor(celula, textos).strip()
        bruto = colunas.get("A", "").removesuffix(".0")
        if not _CODIGO.fullmatch(bruto):
            continue
        codigo = bruto.zfill(6)
        if codigo not in vistos:
            vistos.add(codigo)
            servicos.append((codigo, colunas.get("E", "")))
    return servicos
