"""A documentação oficial em docs/referencia/gov-docs é frozen: confere com o manifesto (T-017)."""

import hashlib

from src.config import RAIZ

GOV_DOCS = RAIZ / "docs" / "referencia" / "gov-docs"
MANIFESTO = GOV_DOCS / "SHA256SUMS"
# Arquivos da pasta que não são documentos oficiais.
NOSSOS = {"SHA256SUMS", "LEIAME.md"}


def _manifesto() -> dict[str, str]:
    pares = {}
    for linha in MANIFESTO.read_text(encoding="utf-8").splitlines():
        if linha.strip():
            sha, nome = linha.split(maxsplit=1)
            pares[nome.strip().lstrip("*")] = sha
    return pares


def _oficiais() -> list[str]:
    return sorted(p.name for p in GOV_DOCS.iterdir() if p.name not in NOSSOS)


def test_manifesto_lista_exatamente_os_arquivos_da_pasta():
    assert sorted(_manifesto()) == _oficiais()


def test_cada_arquivo_bate_com_o_sha256_do_manifesto():
    alterados = [
        nome
        for nome, sha in _manifesto().items()
        if hashlib.sha256((GOV_DOCS / nome).read_bytes()).hexdigest() != sha
    ]
    assert alterados == []


def test_sao_oito_anexos_e_seis_manuais():
    nomes = _oficiais()
    assert len([n for n in nomes if n.startswith("anexo") and n.endswith(".xlsx")]) == 8
    assert len([n for n in nomes if n.startswith("manual") and n.endswith(".pdf")]) == 6
    assert len(nomes) == 14


def test_a_pasta_tem_leiame_com_origem_e_licenca():
    texto = (GOV_DOCS / "LEIAME.md").read_text(encoding="utf-8")
    assert "https://www.gov.br/nfse/" in texto
    assert "creativecommons.org/licenses/by-nd/3.0" in texto
