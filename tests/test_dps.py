import dataclasses
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from lxml import etree

from src.config import RAIZ
from src.dps import (
    NS,
    Dps,
    Prestador,
    Servico,
    Tomador,
    Valores,
    gerar_id,
    localizar_xsd_dps,
    para_xml,
    validar_xml,
)
from src.xsd import preparar_copia_local

BRT = timezone(timedelta(hours=-3))
N = {"n": NS}

# Dados FICTÍCIOS.
CPF_FICTICIO = "12345678909"


def _prestador(**over) -> Prestador:
    base = dict(
        cnpj="11222333000181",
        inscricao_municipal="12345",
        op_simp_nac=3,
        reg_esp_trib=0,
        reg_ap_trib_sn=1,
    )
    base.update(over)
    return Prestador(**base)


def _valores(**over) -> Valores:
    base = dict(v_serv=Decimal("100"), p_tot_trib_sn=Decimal("6.00"))
    base.update(over)
    return Valores(**base)


def _dps(**over) -> Dps:
    base = dict(
        tp_amb=2,
        c_loc_emi="3304557",
        serie=1,
        n_dps=42,
        d_compet=date(2026, 10, 7),
        dh_emi=datetime(2026, 10, 7, 10, 0, 0, tzinfo=BRT),
        prestador=_prestador(),
        tomador=Tomador(nome="Cliente", cnpj="99888777000161"),
        servico=Servico(c_loc_prestacao="3304557", c_trib_nac="010101", descricao="Serviço"),
        valores=_valores(),
    )
    base.update(over)
    return Dps(**base)


@pytest.fixture(scope="module")
def xsd(tmp_path_factory):
    # Cópia local dos XSDs oficiais (ver src/xsd.py): o padrão de `serie` no XSD oficial
    # traz ^ e $, que em XML Schema são caracteres literais.
    copia = preparar_copia_local(
        RAIZ / "schemas" / "1.01", tmp_path_factory.mktemp("xsd") / "1.01-local"
    )
    return localizar_xsd_dps(copia)


def _filhos(raiz, caminho: str) -> list[str]:
    return [etree.QName(el).localname for el in raiz.find(caminho, N)]


def test_id_tem_45_caracteres_e_composicao_correta():
    id_ = gerar_id("3304557", "11222333000181", 1, 42)
    assert len(id_) == 45
    assert id_ == "DPS3304557" + "2" + "11222333000181" + "00001" + "000000000000042"


def test_xml_estrutura_basica():
    raiz = etree.fromstring(para_xml(_dps()))
    assert raiz.tag == f"{{{NS}}}DPS"
    assert raiz.find("n:infDPS", N).get("Id") == _dps().id
    assert raiz.findtext("n:infDPS/n:valores/n:vServPrest/n:vServ", namespaces=N) == "100.00"
    assert raiz.findtext("n:infDPS/n:dhEmi", namespaces=N).endswith("-03:00")


def test_tomador_exige_cnpj_ou_cpf():
    with pytest.raises(ValueError):
        Tomador(nome="X")
    with pytest.raises(ValueError):
        Tomador(nome="X", cnpj="99888777000161", cpf="12345678901")


def test_dh_emi_sem_fuso_e_rejeitada():
    with pytest.raises(ValueError):
        _dps(dh_emi=datetime(2026, 10, 7, 10, 0, 0))


def test_cnpj_invalido_e_rejeitado():
    with pytest.raises(ValueError):
        _prestador(cnpj="123")


def test_xml_valido_contra_xsd_oficial(xsd):
    assert validar_xml(para_xml(_dps()), xsd) == []


# --- Simples Nacional ME/EPP (T-010, DEC-013) -------------------------------------------


def test_me_epp_emite_regaptribsn_e_ptottribsn_sem_indtottrib():
    raiz = etree.fromstring(para_xml(_dps()))
    assert _filhos(raiz, "n:infDPS/n:prest/n:regTrib") == [
        "opSimpNac",
        "regApTribSN",
        "regEspTrib",
    ]
    assert raiz.findtext("n:infDPS/n:prest/n:regTrib/n:regApTribSN", namespaces=N) == "1"
    assert _filhos(raiz, "n:infDPS/n:valores/n:trib/n:totTrib") == ["pTotTribSN"]
    assert raiz.findtext(".//n:pTotTribSN", namespaces=N) == "6.00"
    # E0712: indTotTrib nunca pode ser informado para ME/EPP.
    assert raiz.find(".//n:indTotTrib", N) is None


def test_regaptribsn_e_obrigatorio_para_me_epp():
    with pytest.raises(ValueError, match=r"regApTribSN.*obrigatório"):
        _prestador(reg_ap_trib_sn=None)


@pytest.mark.parametrize("op_simp_nac", [1, 2])
def test_regaptribsn_e_recusado_para_nao_optante_e_mei(op_simp_nac):
    with pytest.raises(ValueError, match="regApTribSN só existe para ME/EPP"):
        _prestador(op_simp_nac=op_simp_nac, reg_ap_trib_sn=1)


@pytest.mark.parametrize(("op_simp_nac", "nome"), [(1, "Não Optante"), (2, "MEI")])
def test_nao_optante_e_mei_ainda_nao_suportados(op_simp_nac, nome):
    # Sem eles, pTotTribSN (proibido para os dois) e indTotTrib (proibido para o
    # Não Optante) nunca chegam ao XML (DEC-022).
    with pytest.raises(ValueError, match=f"{nome}.*ainda não suportado"):
        _prestador(op_simp_nac=op_simp_nac, reg_ap_trib_sn=None)


@pytest.mark.parametrize("reg_ap_trib_sn", [2, 3])
def test_iss_por_fora_do_simples_ainda_nao_suportado(reg_ap_trib_sn):
    with pytest.raises(ValueError, match=r"ainda não suportado.*T-023"):
        _prestador(reg_ap_trib_sn=reg_ap_trib_sn)


@pytest.mark.parametrize(
    ("campo", "valor"),
    [("op_simp_nac", 0), ("op_simp_nac", 4), ("reg_ap_trib_sn", 0), ("reg_ap_trib_sn", 4)],
)
def test_codigos_fora_da_tabela(campo, valor):
    with pytest.raises(ValueError, match=campo):
        _prestador(**{campo: valor})


@pytest.mark.parametrize("reg_esp_trib", [1, 2, 3, 4, 5, 6, 9])
def test_me_epp_pelo_simples_exige_regesptrib_nenhum(reg_esp_trib):
    # Anexo I: regEspTrib = 0 quando opSimpNac = 3 e regApTribSN = 1.
    with pytest.raises(ValueError, match="regEspTrib"):
        _prestador(reg_esp_trib=reg_esp_trib)


@pytest.mark.parametrize(
    ("valor", "texto"),
    [
        (Decimal("0"), "0.00"),
        (Decimal("6"), "6.00"),
        (Decimal("12.5"), "12.50"),
        (Decimal("99.99"), "99.99"),
    ],
)
def test_ptottribsn_sai_com_duas_casas_e_valido_no_xsd(xsd, valor, texto):
    xml = para_xml(_dps(valores=_valores(p_tot_trib_sn=valor)))
    assert etree.fromstring(xml).findtext(".//n:pTotTribSN", namespaces=N) == texto
    assert validar_xml(xml, xsd) == []


@pytest.mark.parametrize(
    "valor",
    [Decimal("-0.01"), Decimal("100"), Decimal("6.123"), Decimal("NaN"), 6.5, "6.00", None],
)
def test_ptottribsn_fora_da_faixa_ou_do_tipo(valor):
    with pytest.raises(ValueError, match="p_tot_trib_sn"):
        _valores(p_tot_trib_sn=valor)


def test_sem_retencao_pAliq_e_recusado():
    # Anexo I: ME/EPP com ISSQN pelo SN e sem retenção não informa pAliq.
    with pytest.raises(ValueError, match="pAliq"):
        _dps(valores=_valores(tp_ret_issqn=1, p_aliq=Decimal("2.00")))


@pytest.mark.parametrize("tp_ret_issqn", [2, 3])
def test_com_retencao_pAliq_e_obrigatorio(tp_ret_issqn):
    with pytest.raises(ValueError, match="pAliq"):
        _dps(valores=_valores(tp_ret_issqn=tp_ret_issqn, p_aliq=None))


def test_com_retencao_e_pAliq_o_xml_e_valido(xsd):
    dps = _dps(valores=_valores(tp_ret_issqn=2, p_aliq=Decimal("2.00")))
    xml = para_xml(dps)
    assert etree.fromstring(xml).findtext(".//n:pAliq", namespaces=N) == "2.00"
    assert validar_xml(xml, xsd) == []


# --- INV-06: nada do emitente fixo em src/ -------------------------------------------------

# Dois emitentes FICTÍCIOS, de municípios e serviços diferentes.
EMITENTES = [
    ("11222333000181", "3304557", "12345", "010101", "Desenvolvimento de software"),
    ("99888777000161", "3550308", None, "010701", "Suporte técnico em informática"),
]
TOMADORES = [
    Tomador(nome="Pessoa Física Fictícia", cpf=CPF_FICTICIO),
    Tomador(nome="Empresa Fictícia Ltda", cnpj="44555666000199"),
]


@pytest.mark.parametrize("tomador", TOMADORES, ids=["cpf", "cnpj"])
@pytest.mark.parametrize("emitente", EMITENTES, ids=["rio", "sao-paulo"])
def test_dps_de_emitentes_diferentes_e_valida(xsd, emitente, tomador):
    cnpj, municipio, im, c_trib_nac, descricao = emitente
    dps = _dps(
        c_loc_emi=municipio,
        prestador=_prestador(cnpj=cnpj, inscricao_municipal=im),
        tomador=tomador,
        servico=Servico(c_loc_prestacao=municipio, c_trib_nac=c_trib_nac, descricao=descricao),
    )
    xml = para_xml(dps)
    assert validar_xml(xml, xsd) == []
    raiz = etree.fromstring(xml)
    assert raiz.findtext("n:infDPS/n:cLocEmi", namespaces=N) == municipio
    assert raiz.findtext("n:infDPS/n:prest/n:CNPJ", namespaces=N) == cnpj
    assert raiz.findtext("n:infDPS/n:prest/n:IM", namespaces=N) == im
    assert raiz.findtext(".//n:cTribNac", namespaces=N) == c_trib_nac
    assert dps.id.startswith(f"DPS{municipio}2{cnpj}")
    if tomador.cpf:
        assert raiz.findtext("n:infDPS/n:toma/n:CPF", namespaces=N) == CPF_FICTICIO
    else:
        assert raiz.findtext("n:infDPS/n:toma/n:CNPJ", namespaces=N) == "44555666000199"


def _defaults(classe) -> dict[str, object]:
    return {
        campo.name: campo.default
        for campo in dataclasses.fields(classe)
        if campo.default is not dataclasses.MISSING
    }


def test_nenhum_default_de_src_carrega_dado_de_emitente():
    # Tudo o que é do emitente (CNPJ, IM, regime) é obrigatório no Prestador; os defaults
    # restantes são do leiaute ou da nota, não de um emitente.
    assert _defaults(Prestador) == {}
    assert _defaults(Tomador) == {"cnpj": None, "cpf": None}
    assert _defaults(Servico) == {}
    assert _defaults(Valores) == {"trib_issqn": 1, "tp_ret_issqn": 1, "p_aliq": None}
    assert _defaults(Dps) == {"ver_aplic": "nfse-poc-0.1", "tp_emit": 1}


# --- faixa de `serie` (T-014, DEC-019) -------------------------------------------------------


@pytest.mark.parametrize("serie", [1, 49999])
def test_serie_nos_limites_do_aplicativo_proprio_e_aceita(xsd, serie):
    dps = _dps(serie=serie)
    assert dps.id[25:30] == f"{serie:05d}"
    assert validar_xml(para_xml(dps), xsd) == []


@pytest.mark.parametrize("serie", [0, 50000, 99999, -1])
def test_serie_fora_da_faixa_do_aplicativo_proprio_e_recusada(serie):
    with pytest.raises(ValueError, match=r"serie deve estar entre 1 e 49999") as erro:
        _dps(serie=serie)
    # A mensagem diz por quê: 50000 a 89999 são dos emissores oficiais (E0010).
    assert "aplicativo próprio" in str(erro.value)
    assert "E0010" in str(erro.value)
