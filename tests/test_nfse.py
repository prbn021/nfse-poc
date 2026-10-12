"""Conferência da NFS-e devolvida pela SEFIN (T-007). Só dados fictícios."""

from pathlib import Path

import pytest

from src.assinatura import assinar_dps
from src.certificado import Certificado
from src.config import RAIZ
from src.nfse import conferir_nfse, localizar_xsd_nfse
from src.xsd import preparar_copia_local
from tests.nfse_ficticia import CHAVE, gerar_nfse
from tests.pfx import chave_de_teste, gerar_certificado

DPS = (Path(__file__).parent / "dados" / "dps-sem-opcionais.xml").read_bytes()
ID_DPS = "DPS330455721122233300018100001000000000000042"


@pytest.fixture(scope="module")
def xsd(tmp_path_factory):
    copia = preparar_copia_local(
        RAIZ / "schemas" / "1.01", tmp_path_factory.mktemp("xsd") / "1.01-local"
    )
    return localizar_xsd_nfse(copia)


@pytest.fixture(scope="module")
def dps_assinada():
    cert = Certificado(certificado=gerar_certificado(), chave=chave_de_teste(), cadeia=())
    return assinar_dps(DPS, cert)


@pytest.fixture(scope="module")
def nfse(dps_assinada):
    return gerar_nfse(dps_assinada)


def test_localiza_o_xsd_da_nfse(xsd):
    assert xsd.name == "NFSe_v1.01.xsd"


def test_nfse_correta_nao_tem_problemas(nfse, xsd):
    assert conferir_nfse(nfse, chave=CHAVE, id_dps=ID_DPS, xsd=xsd) == []


def test_chave_diferente_da_devolvida(nfse, xsd):
    outra = "1" * 50
    problemas = conferir_nfse(nfse, chave=outra, id_dps=ID_DPS, xsd=xsd)
    assert problemas == ["Id da NFS-e não corresponde à chave de acesso devolvida"]


def test_dps_embutida_de_outro_id(nfse, xsd):
    outro = ID_DPS[:-1] + "3"
    problemas = conferir_nfse(nfse, chave=CHAVE, id_dps=outro, xsd=xsd)
    assert problemas == ["a DPS dentro da NFS-e não é a enviada (Id diferente)"]


def test_ambiente_de_producao_e_apontado(dps_assinada, xsd):
    # tpAmb 1 dentro da DPS embutida: a nota não seria de produção restrita (INV-02).
    nfse = gerar_nfse(dps_assinada.replace(b"<tpAmb>2</tpAmb>", b"<tpAmb>1</tpAmb>"))
    problemas = conferir_nfse(nfse, chave=CHAVE, id_dps=ID_DPS, xsd=xsd)
    assert "tpAmb da NFS-e não é 2 (produção restrita)" in problemas


def test_nfse_sem_assinatura(dps_assinada, xsd):
    nfse = gerar_nfse(dps_assinada, assinar=False)
    problemas = conferir_nfse(nfse, chave=CHAVE, id_dps=ID_DPS, xsd=xsd)
    assert "assinatura da NFS-e não confere com o certificado que ela traz" in problemas
    assert any(p.startswith("inválida contra NFSe_v1.01.xsd") for p in problemas)


def test_nfse_alterada_depois_de_assinada(nfse, xsd):
    alterada = nfse.replace(b"<vLiq>100.00</vLiq>", b"<vLiq>999.00</vLiq>", 1)
    problemas = conferir_nfse(alterada, chave=CHAVE, id_dps=ID_DPS, xsd=xsd)
    assert problemas == ["assinatura da NFS-e não confere com o certificado que ela traz"]


@pytest.mark.parametrize("xml", [b"", b"nao e xml", b"<outra/>"])
def test_conteudo_que_nao_e_nfse(xml, xsd):
    problemas = conferir_nfse(xml, chave=CHAVE, id_dps=ID_DPS, xsd=xsd)
    assert problemas == ["o retorno não é uma NFS-e em XML"]
