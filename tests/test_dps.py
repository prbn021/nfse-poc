from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from lxml import etree

from src.config import RAIZ
from src.dps import (NS, Dps, Prestador, Servico, Tomador, Valores, gerar_id,
                     localizar_xsd_dps, para_xml, validar_xml)

BRT = timezone(timedelta(hours=-3))


def _dps(**over) -> Dps:
    base = dict(
        tp_amb=2, c_loc_emi="3304557", serie=1, n_dps=42,
        d_compet=date(2026, 10, 7), dh_emi=datetime(2026, 10, 7, 10, 0, 0, tzinfo=BRT),
        prestador=Prestador(cnpj="11222333000181", inscricao_municipal="12345", op_simp_nac=3),
        tomador=Tomador(nome="Cliente", cnpj="99888777000161"),
        servico=Servico(c_loc_prestacao="3304557", c_trib_nac="010101", descricao="Serviço"),
        valores=Valores(v_serv=Decimal("100")),
    )
    base.update(over)
    return Dps(**base)


def test_id_tem_45_caracteres_e_composicao_correta():
    id_ = gerar_id("3304557", "11222333000181", 1, 42)
    assert len(id_) == 45
    assert id_ == "DPS3304557" + "2" + "11222333000181" + "00001" + "000000000000042"


def test_xml_estrutura_basica():
    raiz = etree.fromstring(para_xml(_dps()))
    ns = {"n": NS}
    assert raiz.tag == f"{{{NS}}}DPS"
    assert raiz.find("n:infDPS", ns).get("Id") == _dps().id
    assert raiz.findtext("n:infDPS/n:valores/n:vServPrest/n:vServ", namespaces=ns) == "100.00"
    assert raiz.findtext("n:infDPS/n:dhEmi", namespaces=ns).endswith("-03:00")


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
        Prestador(cnpj="123", inscricao_municipal=None, op_simp_nac=3)


XSD = localizar_xsd_dps(RAIZ / "schemas")


@pytest.mark.skipif(XSD is None, reason="XSDs oficiais não estão em schemas/")
def test_xml_valido_contra_xsd_oficial():
    assert validar_xml(para_xml(_dps()), XSD) == []
