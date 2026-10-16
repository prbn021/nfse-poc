"""Leitura da chave de acesso da NFS-e (T-043): uma regra só, no domínio, no lugar das cópias
que os scripts tinham. Só dados fictícios."""

import pytest

from src.config import RAIZ
from src.dominio.chave import TIPO_INSCRICAO_CNPJ, cnpj_do_emitente, municipio, tipo_inscricao

# Anexo I, Id da NFS-e: município (7), ambiente gerador (1), tipo de inscrição (1), inscrição
# federal (14), número (13), ano e mês (4), código (9), DV (1).
CHAVE = "3304557" + "1" + "2" + "11222333000181" + "0" * 12 + "7" + "2610" + "1" * 9 + "5"


def test_a_chave_de_exemplo_tem_50_digitos():
    assert len(CHAVE) == 50


def test_municipio_sao_as_posicoes_1_a_7():
    assert municipio(CHAVE) == "3304557"


def test_tipo_de_inscricao_e_a_posicao_9():
    assert tipo_inscricao(CHAVE) == "2" == TIPO_INSCRICAO_CNPJ


def test_cnpj_do_emitente_sao_as_posicoes_10_a_23():
    assert cnpj_do_emitente(CHAVE) == "11222333000181"


@pytest.mark.parametrize("script", ["cancelar.py", "consultar_nfse.py"])
def test_os_scripts_nao_tem_mais_copia_da_leitura(script):
    codigo = (RAIZ / "scripts" / script).read_text(encoding="utf-8")
    assert "_cnpj_da_chave" not in codigo
    assert "[9:23]" not in codigo
    assert "cnpj_do_emitente" in codigo
