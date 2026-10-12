"""Leitura da lista de serviços nacional (Anexo B) para a varredura da T-026."""

import re

import pytest

from src.config import RAIZ
from src.lista_servicos import localizar_anexo_b, servicos_nacionais

GOV_DOCS = RAIZ / "docs" / "referencia" / "gov-docs"


@pytest.fixture(scope="module")
def servicos():
    return servicos_nacionais(localizar_anexo_b(GOV_DOCS))


def test_localiza_o_anexo_b_versionado():
    assert localizar_anexo_b(GOV_DOCS).name.startswith("anexo_b-")


def test_codigos_tem_6_digitos_com_zero_a_esquerda_e_sem_repeticao(servicos):
    codigos = [codigo for codigo, _ in servicos]
    assert all(re.fullmatch(r"\d{6}", codigo) for codigo in codigos)
    assert len(codigos) == len(set(codigos))
    assert len(codigos) > 200


def test_inclui_codigos_conhecidos_com_a_descricao(servicos):
    descricoes = dict(servicos)
    assert descricoes["010101"] == "Análise e desenvolvimento de sistemas."
    assert descricoes["041201"] == "Odontologia."
    assert "990101" in descricoes


def test_linhas_de_item_e_subitem_ficam_de_fora(servicos):
    # Linhas como "1 | 0 | 0" (item) e "1 | 1 | 0" (subitem) não têm código na coluna A.
    assert all(codigo not in ("000001", "000100") for codigo, _ in servicos)


def test_pasta_sem_anexo_b(tmp_path):
    assert localizar_anexo_b(tmp_path) is None
