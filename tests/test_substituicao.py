"""Substituição de NFS-e: grupo `subst` da DPS, leitura da nota substituída e conferência do
evento 105102 (T-031). Sem rede; só dados fictícios.
"""

import dataclasses
from datetime import date
from decimal import Decimal
from functools import partial
from pathlib import Path

import pytest
from lxml import etree

from src.assinatura import assinar_dps, conferir_assinatura_do_sistema
from src.certificado import Certificado
from src.config import XSD_DIR_PADRAO
from src.dominio import evento as dominio_evento
from src.dominio.dps import NS, Substituicao, para_xml, validar_xml
from src.dominio.evento import localizar_xsd_evento
from src.dominio.nfse import ResumoDps, resumo_da_dps
from tests.evento_ficticio import gerar_evento
from tests.nfse_ficticia import CHAVE, gerar_nfse
from tests.pfx import chave_de_teste, gerar_certificado
from tests.test_dps import _dps, xsd  # noqa: F401 (fixture)

# Com o adaptador de assinatura de verdade, como os scripts o montam (T-043).
conferir_substituicao = partial(
    dominio_evento.conferir_substituicao, conferir_assinatura=conferir_assinatura_do_sistema
)

N = {"n": NS}
# Chave fictícia da nota substituída: mesmo município, tipo e CNPJ de _dps(), outro número.
CHAVE_SUBST = CHAVE[:23] + "0000000000003" + CHAVE[36:]
OUTROS = 99
MOTIVO = "Substituicao de teste em producao restrita"


def _subst(**over) -> Substituicao:
    base = dict(chave=CHAVE_SUBST, c_motivo=OUTROS, x_motivo=MOTIVO)
    base.update(over)
    return Substituicao(**base)


# --- modelo -------------------------------------------------------------------------------


@pytest.mark.parametrize("c_motivo", [1, 2, 3, 4, 5, 99])
def test_motivos_aceitos(c_motivo):
    assert _subst(c_motivo=c_motivo).c_motivo == c_motivo


@pytest.mark.parametrize("c_motivo", [0, 6, 98, 100, "01", 1.0, True, None])
def test_motivos_recusados(c_motivo):
    with pytest.raises(ValueError, match="c_motivo"):
        _subst(c_motivo=c_motivo)


def test_outros_exige_descricao():
    with pytest.raises(ValueError, match="E0078"):
        _subst(c_motivo=OUTROS, x_motivo=None)


def test_descricao_e_opcional_nos_demais_motivos():
    assert _subst(c_motivo=5, x_motivo=None).x_motivo is None


@pytest.mark.parametrize(
    "x_motivo",
    [
        "a" * 14,
        "a" * 256,
        " " + MOTIVO,
        MOTIVO + " ",
        "Substituicao de\nteste",
        "Substituicao \u2013 de teste",
    ],
)
def test_descricao_fora_do_tsstring_ou_do_tamanho(x_motivo):
    with pytest.raises(ValueError, match="x_motivo"):
        _subst(x_motivo=x_motivo)


@pytest.mark.parametrize("x_motivo", ["a" * 15, "a" * 255, "Substituição de teste"])
def test_descricao_nos_limites(x_motivo):
    assert _subst(x_motivo=x_motivo).x_motivo == x_motivo


@pytest.mark.parametrize("chave", ["1" * 49, "1" * 51, "a" * 50, None])
def test_chave_fora_do_formato(chave):
    with pytest.raises(ValueError, match="chave"):
        _subst(chave=chave)


@pytest.mark.parametrize(
    ("chave", "campo"),
    [
        ("3550308" + CHAVE_SUBST[7:], "município"),
        (CHAVE_SUBST[:8] + "1" + CHAVE_SUBST[9:], "tipo de inscrição"),
        (CHAVE_SUBST[:9] + "99888777000161" + CHAVE_SUBST[23:], "CNPJ"),
    ],
)
def test_chave_de_outro_emitente_ou_municipio_e_recusada(chave, campo):
    with pytest.raises(ValueError, match=f"E0042.*{campo}|{campo}.*E0042"):
        _dps(subst=_subst(chave=chave))


# --- XML ----------------------------------------------------------------------------------


def _inf(dps) -> etree._Element:
    return etree.fromstring(para_xml(dps)).find("n:infDPS", N)


def test_subst_sai_entre_clocemi_e_prest(xsd):  # noqa: F811
    dps = _dps(subst=_subst())
    filhos = [etree.QName(e).localname for e in _inf(dps)]
    assert filhos[filhos.index("cLocEmi") + 1 : filhos.index("cLocEmi") + 3] == ["subst", "prest"]
    subst = _inf(dps).find("n:subst", N)
    assert [etree.QName(e).localname for e in subst] == ["chSubstda", "cMotivo", "xMotivo"]
    assert subst.findtext("n:chSubstda", namespaces=N) == CHAVE_SUBST
    assert subst.findtext("n:cMotivo", namespaces=N) == "99"
    assert subst.findtext("n:xMotivo", namespaces=N) == MOTIVO
    assert validar_xml(para_xml(dps), xsd) == []


@pytest.mark.parametrize(("c_motivo", "texto"), [(1, "01"), (5, "05")])
def test_motivo_sai_com_dois_digitos_e_sem_descricao(xsd, c_motivo, texto):  # noqa: F811
    dps = _dps(subst=_subst(c_motivo=c_motivo, x_motivo=None))
    subst = _inf(dps).find("n:subst", N)
    assert subst.findtext("n:cMotivo", namespaces=N) == texto
    assert subst.find("n:xMotivo", N) is None
    assert validar_xml(para_xml(dps), xsd) == []


def test_sem_subst_o_xml_nao_muda():
    # O golden da T-018 com o grupo IBS/CBS mínimo (T-034).
    golden = Path(__file__).parent / "dados" / "dps-com-ibscbs.xml"
    assert para_xml(_dps()) == golden.read_bytes()
    assert _inf(_dps()).find("n:subst", N) is None


# --- leitura da nota substituída ------------------------------------------------------------


@pytest.fixture(scope="module")
def nfse_original():
    cert = Certificado(certificado=gerar_certificado(), chave=chave_de_teste(), cadeia=())
    return gerar_nfse(assinar_dps(para_xml(_dps()), cert), chave=CHAVE_SUBST)


def test_resumo_da_dps_embutida(nfse_original):
    assert resumo_da_dps(nfse_original) == ResumoDps(
        d_compet=date(2026, 10, 7), tomador="99888777000161", v_serv=Decimal("100.00")
    )


def test_resumo_com_tomador_cpf():
    dps = _dps(tomador=dataclasses.replace(_dps().tomador, cnpj=None, cpf="12345678909"))
    resumo = resumo_da_dps(gerar_nfse(para_xml(dps), assinar=False))
    assert resumo.tomador == "12345678909"


@pytest.mark.parametrize("xml", [b"", b"nao e xml", b"<outra/>"])
def test_resumo_de_conteudo_que_nao_e_nfse(xml):
    with pytest.raises(ValueError, match="NFS-e"):
        resumo_da_dps(xml)


def test_resumo_sem_dcompet():
    xml = gerar_nfse(para_xml(_dps()), assinar=False)
    xml = xml.replace(b"<dCompet>2026-10-07</dCompet>", b"")
    with pytest.raises(ValueError, match="dCompet"):
        resumo_da_dps(xml)


# --- evento 105102 --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def xsd_evento():
    return localizar_xsd_evento(XSD_DIR_PADRAO)


def test_evento_de_substituicao_correto(xsd_evento):
    evento = gerar_evento(chave=CHAVE_SUBST, tipo="105102", ch_substituta=CHAVE)
    problemas = conferir_substituicao(
        evento, chave_substituida=CHAVE_SUBST, chave_substituta=CHAVE, xsd=xsd_evento
    )
    assert problemas == []


def test_evento_aponta_outra_substituta(xsd_evento):
    outra = CHAVE[:23] + "0000000000009" + CHAVE[36:]
    evento = gerar_evento(chave=CHAVE_SUBST, tipo="105102", ch_substituta=outra)
    problemas = conferir_substituicao(
        evento, chave_substituida=CHAVE_SUBST, chave_substituta=CHAVE, xsd=xsd_evento
    )
    assert problemas == ["o evento 105102 não aponta a nota nova (chSubstituta diferente)"]


def test_evento_de_outro_tipo_na_conferencia_da_substituicao(xsd_evento):
    evento = gerar_evento(chave=CHAVE_SUBST)  # 101101
    problemas = conferir_substituicao(
        evento, chave_substituida=CHAVE_SUBST, chave_substituta=CHAVE, xsd=xsd_evento
    )
    assert "o evento não é do tipo pedido (105102)" in problemas
