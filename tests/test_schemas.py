"""Pacotes oficiais de XSD em schemas/: frozen, um por pasta, com manifesto (T-038, DEC-066)."""

import hashlib

import pytest
from lxml import etree

from src.config import RAIZ, XSD_DIR_PADRAO
from src.dps import NS, localizar_xsd_dps, para_xml, validar_xml
from tests.test_dps import _dps

SCHEMAS = RAIZ / "schemas"
ARQUIVOS_DO_PACOTE = [
    "CNC_v1.00.xsd",
    "DPS_v1.01.xsd",
    "NFSe_v1.01.xsd",
    "evento_v1.01.xsd",
    "pedRegEvento_v1.01.xsd",
    "tiposCnc_v1.00.xsd",
    "tiposComplexos_v1.01.xsd",
    "tiposEventos_v1.01.xsd",
    "tiposSimples_v1.01.xsd",
    "xmldsig-core-schema.xsd",
]


def _pacotes() -> list:
    return sorted(p for p in SCHEMAS.iterdir() if p.is_dir())


def _manifesto(pasta) -> dict[str, str]:
    pares = {}
    for linha in (pasta / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        if linha.strip():
            sha, nome = linha.split(maxsplit=1)
            pares[nome.strip().lstrip("*")] = sha
    return pares


def _com_serie(serie: str) -> bytes:
    raiz = etree.fromstring(para_xml(_dps()))
    raiz.find("n:infDPS/n:serie", {"n": NS}).text = serie
    return etree.tostring(raiz)


def test_so_o_pacote_de_producao_restrita_esta_no_repositorio():
    # A schemas/1.01 (pacote de produção 20260209) saiu na T-038; nada de cópia -local.
    assert [p.name for p in _pacotes()] == ["v1.01-prodrest-20260727"]


def test_o_pacote_ativo_e_uma_pasta_de_schemas():
    assert XSD_DIR_PADRAO in _pacotes()


@pytest.mark.parametrize("pasta", _pacotes(), ids=lambda p: p.name)
def test_manifesto_lista_exatamente_os_arquivos_da_pasta(pasta):
    oficiais = sorted(p.name for p in pasta.iterdir() if p.name != "SHA256SUMS")
    assert sorted(_manifesto(pasta)) == oficiais


@pytest.mark.parametrize("pasta", _pacotes(), ids=lambda p: p.name)
def test_cada_arquivo_bate_com_o_sha256_do_manifesto(pasta):
    alterados = [
        nome
        for nome, sha in _manifesto(pasta).items()
        if hashlib.sha256((pasta / nome).read_bytes()).hexdigest() != sha
    ]
    assert alterados == []


def test_o_pacote_ativo_tem_os_dez_arquivos_do_zip():
    assert sorted(_manifesto(XSD_DIR_PADRAO)) == sorted(ARQUIVOS_DO_PACOTE)


def test_leiame_tem_origem_licenca_e_sha256_do_zip():
    texto = (SCHEMAS / "LEIAME.md").read_text(encoding="utf-8")
    assert "esquemas-nfse-rtc-v1-01-20260727.zip" in texto
    assert "6c7e0510d3ecff4454f291f4e10b742d27a4818f23aab181494f96d0ea79f3dc" in texto
    assert "creativecommons.org/licenses/by-nd/3.0" in texto


def test_xml_de_exemplo_valido_direto_contra_o_pacote_ativo():
    assert validar_xml(para_xml(_dps()), localizar_xsd_dps(XSD_DIR_PADRAO)) == []


@pytest.mark.parametrize("serie", ["1", "00001", "49999"])
def test_serie_valida_e_aceita(serie):
    assert validar_xml(_com_serie(serie), localizar_xsd_dps(XSD_DIR_PADRAO)) == []


@pytest.mark.parametrize("serie", ["abc", "123456", "", "^1$", "1a", "99999"])
def test_serie_invalida_e_rejeitada(serie):
    # Padrão do pacote: [0-9]{1,4}|[0-8][0-9]{4}, sem as âncoras do pacote de produção.
    erros = validar_xml(_com_serie(serie), localizar_xsd_dps(XSD_DIR_PADRAO))
    assert erros and "serie" in erros[0]
