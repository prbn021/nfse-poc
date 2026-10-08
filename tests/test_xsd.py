import pytest
from lxml import etree

from src.config import RAIZ
from src.dps import NS, localizar_xsd_dps, para_xml, validar_xml
from src.xsd import dir_local, preparar_copia_local, remover_ancoras
from tests.test_dps import _dps

OFICIAL = RAIZ / "schemas" / "1.01"

# Únicas linhas em que a cópia local pode diferir dos XSDs oficiais (arquivo, linha).
DIFERENCAS_ESPERADAS = {("tiposSimples_v1.01.xsd", 161)}


@pytest.fixture(scope="module")
def copia(tmp_path_factory):
    destino = tmp_path_factory.mktemp("xsd") / "1.01-local"
    preparar_copia_local(OFICIAL, destino)
    return destino


def _com_serie(serie: str) -> bytes:
    raiz = etree.fromstring(para_xml(_dps()))
    raiz.find("n:infDPS/n:serie", {"n": NS}).text = serie
    return etree.tostring(raiz)


@pytest.mark.parametrize("antes, depois", [
    (rb'<xs:pattern value="^0{0,4}\d{1,5}$"/>', rb'<xs:pattern value="0{0,4}\d{1,5}"/>'),
    (rb'<xsd:pattern  value="^abc"/>', rb'<xsd:pattern  value="abc"/>'),
    (rb'<xs:pattern value="abc$"/>', rb'<xs:pattern value="abc"/>'),
])
def test_remover_ancoras_tira_so_o_inicio_e_o_fim(antes, depois):
    assert remover_ancoras(antes) == depois


@pytest.mark.parametrize("intacto", [
    rb'<xs:pattern value="[^0-9]{3}"/>',          # ^ de negação dentro de [...]
    rb'<xs:pattern value="a^b$c"/>',              # ^ e $ no meio
    rb'<xs:pattern value="R\$"/>',                # $ escapado
    rb'<xs:enumeration value="^1$"/>',            # não é pattern
    rb'<xs:pattern value="DPS[0-9]{42}"/>',
])
def test_remover_ancoras_nao_toca_no_resto(intacto):
    assert remover_ancoras(intacto) == intacto


def test_dir_local_fica_ao_lado_do_oficial():
    assert dir_local(OFICIAL) == RAIZ / "schemas" / "1.01-local"


def test_copia_nunca_sobrescreve_os_oficiais():
    with pytest.raises(ValueError):
        preparar_copia_local(OFICIAL, OFICIAL)


def test_copia_difere_dos_oficiais_so_nas_ancoras(copia):
    oficiais = sorted(f.name for f in OFICIAL.glob("*.xsd"))
    assert sorted(f.name for f in copia.glob("*.xsd")) == oficiais

    diferencas = set()
    for nome in oficiais:
        a = (OFICIAL / nome).read_bytes().split(b"\n")
        b = (copia / nome).read_bytes().split(b"\n")
        assert len(a) == len(b), nome
        for n, (la, lb) in enumerate(zip(a, b), start=1):
            if la != lb:
                diferencas.add((nome, n))
                assert b"pattern" in la
                assert lb == la.replace(b'"^', b'"').replace(b'$"', b'"')
    assert diferencas == DIFERENCAS_ESPERADAS


def test_xml_valido_contra_a_copia_local(copia):
    assert validar_xml(para_xml(_dps()), localizar_xsd_dps(copia)) == []


@pytest.mark.parametrize("serie", ["1", "00001", "99999"])
def test_serie_valida_e_aceita(copia, serie):
    assert validar_xml(_com_serie(serie), localizar_xsd_dps(copia)) == []


@pytest.mark.parametrize("serie", ["abc", "123456", "", "^1$", "1a"])
def test_serie_invalida_continua_rejeitada(copia, serie):
    erros = validar_xml(_com_serie(serie), localizar_xsd_dps(copia))
    assert erros and "serie" in erros[0]
