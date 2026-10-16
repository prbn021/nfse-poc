"""Grupo IBS/CBS na DPS (T-034, DEC-069): modelo, recusas, XML e golden."""

from datetime import date
from pathlib import Path

import pytest
from lxml import etree

from src.config import XSD_DIR_PADRAO
from src.dominio.dps import (
    C_IND_OP_IMOVEL,
    C_IND_OP_NFSE,
    CODIGOS_DE_OBRA_SEM_IMOVEL,
    IBSCBS_OBRIGATORIO_DESDE,
    IBSCBS_PERMITIDO_DESDE,
    NS,
    IbsCbs,
    Obra,
    Servico,
    localizar_xsd_dps,
    para_xml,
    validar_xml,
)
from tests.test_dps import GOLDEN, _dps, _ibs_cbs

N = {"n": NS}
GOLDEN_IBSCBS = Path(__file__).parent / "dados" / "dps-com-ibscbs.xml"
ANTES_DA_E0855 = date(2026, 9, 30)
# Grupo mínimo, na ordem de TCRTCInfoIBSCBS e TCRTCInfoTributosSitClas (XSD ativo).
GRUPO_MINIMO = (
    b"<IBSCBS><finNFSe>0</finNFSe><cIndOp>100301</cIndOp><indDest>0</indDest>"
    b"<valores><trib><gIBSCBS><CST>000</CST><cClassTrib>000001</cClassTrib></gIBSCBS>"
    b"</trib></valores></IBSCBS>"
)


@pytest.fixture(scope="module")
def xsd():
    return localizar_xsd_dps(XSD_DIR_PADRAO)


def _servico_sem_nbs() -> Servico:
    return Servico(c_loc_prestacao="3304557", c_trib_nac="010101", descricao="Serviço")


def _grupo(dps) -> etree._Element:
    return etree.fromstring(para_xml(dps)).find("n:infDPS/n:IBSCBS", N)


def _filhos(el) -> list[str]:
    return [etree.QName(f).localname for f in el]


# --- constantes, com a fonte -------------------------------------------------------------


def test_cind_op_sao_os_28_codigos_do_anexo_vii_para_nfse():
    assert len(C_IND_OP_NFSE) == 28
    assert {"100301", "020201", "030101", "050101", "100601"} <= C_IND_OP_NFSE
    # Só da NF-e (010104, 010105), só da NFS-e Via (080101) ou sem documento (090101).
    assert not {"010104", "010105", "080101", "090101", "110101"} & C_IND_OP_NFSE
    # Do Anexo C v1.01, retirados no Anexo VII v1.03.00.
    assert not {"030103", "030104", "050103", "050104"} & C_IND_OP_NFSE


def test_codigos_de_imovel_e_de_obra_da_e0932():
    assert {"020101", "020201", "020202", "020301", "020401"} == C_IND_OP_IMOVEL
    assert C_IND_OP_IMOVEL <= C_IND_OP_NFSE
    assert len(CODIGOS_DE_OBRA_SEM_IMOVEL) == 11
    assert "070201" in CODIGOS_DE_OBRA_SEM_IMOVEL
    assert "141403" not in CODIGOS_DE_OBRA_SEM_IMOVEL


def test_datas_das_regras_e0850_e_e0855():
    assert date(2026, 1, 1) == IBSCBS_PERMITIDO_DESDE
    assert date(2026, 10, 1) == IBSCBS_OBRIGATORIO_DESDE


# --- modelo ------------------------------------------------------------------------------


def test_cst_vem_dos_tres_primeiros_digitos_do_cclasstrib():
    assert IbsCbs(c_ind_op="100301", c_class_trib="000001").cst == "000"
    assert IbsCbs(c_ind_op="100301", c_class_trib="200052").cst == "200"


@pytest.mark.parametrize("codigo", ["10030", "1003011", "10030a", "", None, 100301])
def test_cind_op_fora_de_6_digitos_e_recusado(codigo):
    with pytest.raises(ValueError, match="c_ind_op"):
        IbsCbs(c_ind_op=codigo, c_class_trib="000001")


@pytest.mark.parametrize("codigo", ["010104", "080101", "090101", "030103", "999999"])
def test_cind_op_fora_do_anexo_vii_para_nfse_e_recusado(codigo):
    with pytest.raises(ValueError, match="E0901"):
        IbsCbs(c_ind_op=codigo, c_class_trib="000001")


@pytest.mark.parametrize("codigo", ["00000", "0000011", "00000a", "", None, 1])
def test_cclasstrib_fora_de_6_digitos_e_recusado(codigo):
    with pytest.raises(ValueError, match="c_class_trib"):
        IbsCbs(c_ind_op="100301", c_class_trib=codigo)


@pytest.mark.parametrize("valor", [0, 1])
def test_ind_final_0_e_1_aceitos(valor):
    assert IbsCbs(c_ind_op="100301", c_class_trib="000001", ind_final=valor).ind_final == valor


@pytest.mark.parametrize("valor", [2, -1, True, "1"])
def test_ind_final_fora_de_0_e_1_e_recusado(valor):
    with pytest.raises(ValueError, match="ind_final"):
        IbsCbs(c_ind_op="100301", c_class_trib="000001", ind_final=valor)


# --- regras da DPS -----------------------------------------------------------------------


def test_sem_grupo_a_partir_de_outubro_de_2026_e_recusado():
    with pytest.raises(ValueError, match="E0855"):
        _dps(d_compet=IBSCBS_OBRIGATORIO_DESDE, ibs_cbs=None)


def test_sem_grupo_antes_de_outubro_de_2026_e_aceito():
    assert _dps(d_compet=ANTES_DA_E0855, ibs_cbs=None).ibs_cbs is None


def test_grupo_antes_de_2026_e_recusado():
    with pytest.raises(ValueError, match="E0850"):
        _dps(d_compet=date(2025, 12, 31))


def test_grupo_a_partir_de_2026_e_aceito():
    assert _dps(d_compet=IBSCBS_PERMITIDO_DESDE).ibs_cbs == _ibs_cbs()


@pytest.mark.parametrize("codigo", sorted(C_IND_OP_IMOVEL))
def test_cind_op_de_imovel_fora_de_obra_ainda_nao_suportado(codigo):
    with pytest.raises(ValueError, match="E0932") as erro:
        _dps(ibs_cbs=_ibs_cbs(c_ind_op=codigo))
    assert "ainda não suportado" in str(erro.value)


def test_cind_op_de_imovel_em_servico_de_obra_e_aceito(xsd):
    servico = Servico(
        c_loc_prestacao="3304557",
        c_trib_nac="070202",
        descricao="Obra",
        obra=Obra(c_obra="900000000001"),
        c_nbs="115021000",
    )
    dps = _dps(servico=servico, ibs_cbs=_ibs_cbs(c_ind_op="020201", c_class_trib="200046"))
    assert validar_xml(para_xml(dps), xsd) == []


def test_codigo_99_03_exige_cind_op_de_imovel():
    servico = Servico(
        c_loc_prestacao="3304557", c_trib_nac="990301", descricao="Serviço", c_nbs="110021000"
    )
    with pytest.raises(ValueError, match="E0902"):
        _dps(servico=servico, ibs_cbs=_ibs_cbs(c_ind_op="100301"))


# --- XML ---------------------------------------------------------------------------------


def test_grupo_vem_depois_de_valores_na_ordem_do_xsd(xsd):
    dps = _dps()
    xml = para_xml(dps)
    assert validar_xml(xml, xsd) == []
    inf = etree.fromstring(xml).find("n:infDPS", N)
    assert _filhos(inf)[-2:] == ["valores", "IBSCBS"]
    grupo = inf.find("n:IBSCBS", N)
    assert _filhos(grupo) == ["finNFSe", "cIndOp", "indDest", "valores"]
    assert [el.text for el in grupo[:3]] == ["0", "100301", "0"]
    g = grupo.find("n:valores/n:trib/n:gIBSCBS", N)
    assert _filhos(g) == ["CST", "cClassTrib"]
    assert [el.text for el in g] == ["000", "000001"]


def test_ind_final_sai_entre_finnfse_e_cindop(xsd):
    dps = _dps(ibs_cbs=_ibs_cbs(ind_final=1))
    assert validar_xml(para_xml(dps), xsd) == []
    grupo = _grupo(dps)
    assert _filhos(grupo) == ["finNFSe", "indFinal", "cIndOp", "indDest", "valores"]
    assert grupo.findtext("n:indFinal", namespaces=N) == "1"


@pytest.mark.parametrize("codigo", sorted(C_IND_OP_NFSE - C_IND_OP_IMOVEL))
def test_cada_cind_op_aceito_valida_contra_o_xsd(xsd, codigo):
    assert validar_xml(para_xml(_dps(ibs_cbs=_ibs_cbs(c_ind_op=codigo))), xsd) == []


def test_xml_com_grupo_igual_ao_golden():
    # Golden escrito à mão a partir do XSD: o da T-018 com o grupo IBSCBS mínimo.
    assert para_xml(_dps()) == GOLDEN_IBSCBS.read_bytes()


def test_sem_grupo_o_xml_e_o_da_t018():
    # O golden da T-018 tem competência 2026-10-07; sem o grupo, a DPS precisa de uma
    # competência anterior a 01/10/2026 (E0855), e só o dCompet muda.
    dps = _dps(d_compet=ANTES_DA_E0855, ibs_cbs=None, servico=_servico_sem_nbs())
    esperado = GOLDEN.read_bytes().replace(
        b"<dCompet>2026-10-07</dCompet>", b"<dCompet>2026-09-30</dCompet>"
    )
    assert para_xml(dps) == esperado
    assert b"IBSCBS" not in esperado


def test_golden_com_grupo_e_o_da_t018_mais_o_nbs_e_o_grupo():
    # O NBS é exigido com o grupo (E0322) e vem depois de xDescServ (TCCServ).
    esperado = (
        GOLDEN.read_bytes()
        .replace(b"</xDescServ>", b"</xDescServ><cNBS>115021000</cNBS>")
        .replace(b"</infDPS>", GRUPO_MINIMO + b"</infDPS>")
    )
    assert GOLDEN_IBSCBS.read_bytes() == esperado


# --- NBS (E0322; ajuste depois da recusa da produção restrita em 2026-10-14, DEC-070) ----


def test_grupo_sem_nbs_e_recusado():
    with pytest.raises(ValueError, match="E0322"):
        _dps(servico=_servico_sem_nbs())


def test_nbs_sem_grupo_e_aceito(xsd):
    dps = _dps(d_compet=ANTES_DA_E0855, ibs_cbs=None)
    assert validar_xml(para_xml(dps), xsd) == []


@pytest.mark.parametrize("codigo", ["12301230", "1230123000", "1.2301.23.00", "12301230a", ""])
def test_nbs_fora_de_9_digitos_e_recusado(codigo):
    with pytest.raises(ValueError, match="c_nbs"):
        Servico(c_loc_prestacao="3304557", c_trib_nac="010101", descricao="S", c_nbs=codigo)


def test_nbs_sai_depois_de_xdescserv(xsd):
    xml = para_xml(_dps())
    assert validar_xml(xml, xsd) == []
    cserv = etree.fromstring(xml).find("n:infDPS/n:serv/n:cServ", N)
    assert _filhos(cserv) == ["cTribNac", "xDescServ", "cNBS"]
    assert cserv.findtext("n:cNBS", namespaces=N) == "115021000"


@pytest.mark.parametrize(
    ("nbs", "aceito"), [("110021000", True), ("110022000", True), ("115021000", False)]
)
def test_codigo_99_03_so_aceita_os_nbs_da_regra_448(nbs, aceito):
    servico = Servico(c_loc_prestacao="3304557", c_trib_nac="990301", descricao="S", c_nbs=nbs)
    # 020102 (BICE): o único 02XXXX que não exige o grupo imovel (E0932).
    ibs = _ibs_cbs(c_ind_op="020102")
    if aceito:
        assert _dps(servico=servico, ibs_cbs=ibs).servico.c_nbs == nbs
    else:
        with pytest.raises(ValueError, match=r"1\.1002\.10\.00"):
            _dps(servico=servico, ibs_cbs=ibs)
