"""Pedido de registro do evento de cancelamento (101101): modelo, XML e assinatura (T-029, DEC-052).

Sem rede. Só certificado autoassinado (DEC-014) e dados fictícios.
"""

import logging
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from lxml import etree
from signxml import SignatureConfiguration, XMLVerifier
from signxml.exceptions import SignXMLException

import src.assinatura as assinatura
from src.assinatura import assinar_dps, assinar_pedido_evento, conferir_assinatura
from src.certificado import Certificado
from src.config import XSD_DIR_PADRAO
from src.dps import NS, validar_xml
from src.evento import (
    CANCELAMENTO,
    PedidoCancelamento,
    localizar_xsd_pedido_evento,
    para_xml_pedido,
)
from tests.nfse_ficticia import CHAVE
from tests.pfx import CNPJ, chave_de_teste, gerar_certificado

DS = "http://www.w3.org/2000/09/xmldsig#"
N = {"n": NS, "ds": DS}
EXC_C14N = "http://www.w3.org/2001/10/xml-exc-c14n#"
ENVELOPED = "http://www.w3.org/2000/09/xmldsig#enveloped-signature"
RSA_SHA256 = "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"
SHA256 = "http://www.w3.org/2001/04/xmlenc#sha256"

GOLDEN = Path(__file__).parent / "dados" / "pedido-cancelamento.xml"
BRT = timezone(timedelta(hours=-3))
ID = f"PRE{CHAVE}101101"


def _pedido(**kw) -> PedidoCancelamento:
    campos = {
        "chave": CHAVE,
        "cnpj_autor": CNPJ,
        "tp_amb": 2,
        "dh_evento": datetime(2026, 10, 13, 10, 0, 0, tzinfo=BRT),
        "c_motivo": 1,
        "x_motivo": "Erro na emissão da nota de teste",
    }
    campos.update(kw)
    return PedidoCancelamento(**campos)


def _cert(**kw) -> Certificado:
    return Certificado(certificado=gerar_certificado(**kw), chave=chave_de_teste(), cadeia=())


@pytest.fixture(scope="module")
def cert() -> Certificado:
    return _cert()


@pytest.fixture(scope="module")
def xml() -> bytes:
    return para_xml_pedido(_pedido())


@pytest.fixture(scope="module")
def assinado(xml, cert) -> bytes:
    return assinar_pedido_evento(xml, cert)


@pytest.fixture(scope="module")
def xsd():
    return localizar_xsd_pedido_evento(XSD_DIR_PADRAO)


# --- (1) modelo ----------------------------------------------------------------------------


def test_codigo_do_evento_de_cancelamento():
    assert CANCELAMENTO == "101101"


def test_pedido_valido_e_imutavel():
    pedido = _pedido()
    assert pedido.ver_aplic == "nfse-poc-0.1"
    assert pedido.id == ID
    with pytest.raises(AttributeError):
        pedido.c_motivo = 2


@pytest.mark.parametrize(
    "chave",
    [CHAVE[:-1], CHAVE + "0", CHAVE[:-1] + "A", "", None],
)
def test_chave_fora_de_50_digitos(chave):
    with pytest.raises(ValueError, match="chave deve ter 50 dígitos"):
        _pedido(chave=chave)


def test_chave_de_emitente_com_cpf_e_recusada():
    chave_cpf = CHAVE[:8] + "1" + CHAVE[9:]
    with pytest.raises(ValueError, match="CNPJ"):
        _pedido(chave=chave_cpf)


@pytest.mark.parametrize("cnpj", [CNPJ[:-1], CNPJ + "1", "1122233300018A", ""])
def test_cnpj_autor_fora_de_14_digitos(cnpj):
    with pytest.raises(ValueError, match="cnpj_autor deve ter 14 dígitos"):
        _pedido(cnpj_autor=cnpj)


def test_autor_que_nao_e_o_emitente_da_nota_e0813():
    with pytest.raises(ValueError, match="E0813"):
        _pedido(cnpj_autor="99888777000161")


@pytest.mark.parametrize("tp_amb", [0, 3, "2"])
def test_tp_amb_fora_de_1_e_2(tp_amb):
    with pytest.raises(ValueError, match="tp_amb"):
        _pedido(tp_amb=tp_amb)


def test_dh_evento_sem_fuso():
    with pytest.raises(ValueError, match="fuso"):
        _pedido(dh_evento=datetime(2026, 10, 13, 10, 0, 0))


def test_dh_evento_com_fuso_que_nao_e_de_hora_cheia():
    meia_hora = timezone(-timedelta(hours=3, minutes=30))
    with pytest.raises(ValueError, match="hora cheia"):
        _pedido(dh_evento=datetime(2026, 10, 13, 10, 0, 0, tzinfo=meia_hora))


def test_dh_evento_com_microssegundos_sai_sem_eles():
    pedido = _pedido(dh_evento=datetime(2026, 10, 13, 10, 0, 0, 123456, tzinfo=BRT))
    assert b"<dhEvento>2026-10-13T10:00:00-03:00</dhEvento>" in para_xml_pedido(pedido)


@pytest.mark.parametrize("c_motivo", [1, 2, 9])
def test_c_motivo_aceito(c_motivo):
    assert _pedido(c_motivo=c_motivo).c_motivo == c_motivo


@pytest.mark.parametrize("c_motivo", [0, 3, 99, "1", "1 "])
def test_c_motivo_fora_de_1_2_e_9(c_motivo):
    with pytest.raises(ValueError, match="c_motivo"):
        _pedido(c_motivo=c_motivo)


@pytest.mark.parametrize("tamanho", [15, 255])
def test_x_motivo_nos_limites(tamanho):
    assert len(_pedido(x_motivo="a" * tamanho).x_motivo) == tamanho


@pytest.mark.parametrize("tamanho", [14, 256])
def test_x_motivo_fora_de_15_a_255(tamanho):
    with pytest.raises(ValueError, match="15 a 255"):
        _pedido(x_motivo="a" * tamanho)


@pytest.mark.parametrize(
    "texto",
    [" Erro na emissão da nota", "Erro na emissão da nota ", "Erro na emissão\nda nota"],
)
def test_x_motivo_com_espaco_nas_pontas_ou_quebra_de_linha(texto):
    with pytest.raises(ValueError, match="x_motivo"):
        _pedido(x_motivo=texto)


@pytest.mark.parametrize(
    "texto",
    [
        "Erro na emissão \u2013 teste",  # travessão
        "Erro \u201cna\u201d emissão da nota",  # aspas curvas
        "Erro \U0001f600 na emissão",  # emoji
    ],
)
def test_x_motivo_com_caractere_fora_do_tsstring(texto):
    with pytest.raises(ValueError, match="U\\+0020 a U\\+00FF"):
        _pedido(x_motivo=texto)


def test_x_motivo_com_acentos_do_portugues_e_aceito(xsd):
    texto = "Serviço não prestado; ação à vista: ÁÉÍÓÚ çãõ"
    assert validar_xml(para_xml_pedido(_pedido(x_motivo=texto)), xsd) == []


def test_ver_aplic_fora_de_1_a_20():
    with pytest.raises(ValueError, match="ver_aplic"):
        _pedido(ver_aplic="x" * 21)
    with pytest.raises(ValueError, match="ver_aplic"):
        _pedido(ver_aplic="")


# --- (2) XML -------------------------------------------------------------------------------


def test_localiza_o_xsd_do_pedido(xsd):
    assert xsd.name == "pedRegEvento_v1.01.xsd"


def test_xml_igual_ao_golden(xml):
    assert xml == GOLDEN.read_bytes()


def test_xml_e_valido_contra_o_xsd(xml, xsd):
    assert validar_xml(xml, xsd) == []


def test_id_e_pre_chave_e_codigo_do_evento_e1827(xml):
    inf = etree.fromstring(xml).find("n:infPedReg", N)
    assert inf.get("Id") == ID
    assert len(ID) == 59


def test_ordem_dos_elementos(xml):
    inf = etree.fromstring(xml).find("n:infPedReg", N)
    nomes = [etree.QName(el).localname for el in inf]
    assert nomes == ["tpAmb", "verAplic", "dhEvento", "CNPJAutor", "chNFSe", "e101101"]
    grupo = inf.find("n:e101101", N)
    assert [etree.QName(el).localname for el in grupo] == ["xDesc", "cMotivo", "xMotivo"]
    assert grupo.findtext("n:xDesc", namespaces=N) == "Cancelamento de NFS-e"


@pytest.mark.parametrize("c_motivo", [2, 9])
def test_xml_valido_com_cada_motivo(c_motivo, xsd):
    assert validar_xml(para_xml_pedido(_pedido(c_motivo=c_motivo)), xsd) == []


def test_xml_valido_em_producao_so_como_dado(xsd):
    # tp_amb 1 é aceito pelo modelo, como no Dps; a trava de produção é da configuração
    # e do cliente (INV-02).
    xml = para_xml_pedido(_pedido(tp_amb=1))
    assert b"<tpAmb>1</tpAmb>" in xml
    assert validar_xml(xml, xsd) == []


# --- (3) e (5) assinatura -----------------------------------------------------------------


def _verificar(xml: bytes, cert: Certificado):
    return XMLVerifier().verify(
        xml, x509_cert=cert.certificado, expect_config=SignatureConfiguration(location="./")
    )


def test_pedido_assinado_e_valido_contra_o_xsd(assinado, xsd):
    assert validar_xml(assinado, xsd) == []


def test_assinatura_e_irma_depois_do_infpedreg(assinado):
    raiz = etree.fromstring(assinado)
    assert [el.tag for el in raiz] == [f"{{{NS}}}infPedReg", f"{{{DS}}}Signature"]


def test_sem_prefixo_de_namespace(assinado):
    assert all(el.prefix is None for el in etree.fromstring(assinado).iter())
    assert b"xmlns:" not in assinado


def test_perfil_do_pedido(assinado):
    # Como o da DPS, mas com exc-c14n sem comentários: com comentários, a SEFIN respondeu
    # HTTP 500 sem códigos aos dois primeiros cancelamentos reais (T-030, DEC-054).
    sig = etree.fromstring(assinado).find("ds:Signature", N)
    algoritmos = lambda caminho, raiz=sig: [el.get("Algorithm") for el in raiz.findall(caminho, N)]  # noqa: E731
    assert algoritmos("ds:SignedInfo/ds:CanonicalizationMethod") == [EXC_C14N]
    assert algoritmos("ds:SignedInfo/ds:SignatureMethod") == [RSA_SHA256]
    referencias = sig.findall("ds:SignedInfo/ds:Reference", N)
    assert [r.get("URI") for r in referencias] == [f"#{ID}"]
    assert algoritmos("ds:Transforms/ds:Transform", referencias[0]) == [
        ENVELOPED,
        EXC_C14N,
    ]
    assert algoritmos("ds:DigestMethod", referencias[0]) == [SHA256]
    key_info = sig.find("ds:KeyInfo", N)
    assert len(key_info.findall("ds:X509Data/ds:X509Certificate", N)) == 1


def test_verificador_independente_confirma_o_infpedreg(assinado, cert):
    resultado = _verificar(assinado, cert)
    assert etree.QName(resultado.signed_xml).localname == "infPedReg"
    assert resultado.signed_xml.get("Id") == ID


def test_conferir_assinatura_aceita_o_pedido(assinado, cert):
    conferir_assinatura(assinado, cert.certificado)


@pytest.mark.parametrize(
    ("de", "para"),
    [
        (b"<cMotivo>1<", b"<cMotivo>2<"),
        (b"nota de teste<", b"nota de testE<"),
        (b"<tpAmb>2</tpAmb>", b"<tpAmb>1</tpAmb>"),
    ],
)
def test_alterar_o_infpedreg_invalida_a_assinatura(assinado, cert, de, para):
    adulterado = assinado.replace(de, para, 1)
    assert adulterado != assinado
    with pytest.raises(SignXMLException):
        _verificar(adulterado, cert)
    with pytest.raises(ValueError, match="assinatura inválida"):
        conferir_assinatura(adulterado, cert.certificado)


def test_comentario_fica_fora_da_assinatura(assinado, cert):
    # Consequência da canonicalização sem comentários (DEC-054): um comentário inserido no
    # infPedReg não muda o que foi assinado. O conteúdo continua protegido (teste acima).
    com_comentario = assinado.replace(b"<tpAmb>2</tpAmb>", b"<tpAmb>2</tpAmb><!-- x -->", 1)
    assert com_comentario != assinado
    _verificar(com_comentario, cert)
    conferir_assinatura(com_comentario, cert.certificado)


def test_mesma_entrada_gera_a_mesma_saida(xml, cert, assinado):
    assert assinar_pedido_evento(xml, cert) == assinado


def test_assinar_dps_continua_recusando_pedido(xml, cert):
    with pytest.raises(ValueError, match="raiz não é DPS"):
        assinar_dps(xml, cert)


# --- (4) recusas da assinatura ------------------------------------------------------------


@pytest.mark.parametrize(
    ("entrada", "trecho"),
    [
        (b"isto nao e xml", "não é XML"),
        (b"", "não é XML"),
        (f'<DPS xmlns="{NS}" versao="1.01"/>'.encode(), "raiz não é pedRegEvento"),
        (b'<pedRegEvento versao="1.01"/>', "raiz não é pedRegEvento"),
        (f'<pedRegEvento xmlns="{NS}" versao="1.01"/>'.encode(), "sem infPedReg"),
        (
            f'<pedRegEvento xmlns="{NS}" versao="1.01"><infPedReg/></pedRegEvento>'.encode(),
            "infPedReg sem Id",
        ),
    ],
)
def test_xml_fora_do_formato_gera_erro_claro(cert, entrada, trecho):
    with pytest.raises(ValueError, match=trecho):
        assinar_pedido_evento(entrada, cert)


def test_pedido_ja_assinado_e_recusado(assinado, cert):
    with pytest.raises(ValueError, match="já está assinado"):
        assinar_pedido_evento(assinado, cert)


def test_certificado_de_outro_cnpj_e_recusado_e1991():
    outro = _cert(cn="OUTRA EMPRESA FICTICIA:99888777000161", cnpj_no_san="99888777000161")
    with pytest.raises(ValueError, match="E1991"):
        assinar_pedido_evento(para_xml_pedido(_pedido()), outro)


def test_certificado_de_outra_filial_e_recusado():
    # Mesma base de 8 dígitos (E0812 a aceitaria); o projeto exige o CNPJ inteiro.
    filial = CNPJ[:8] + "000262"
    outro = _cert(cn=f"FILIAL FICTICIA:{filial}", cnpj_no_san=filial)
    with pytest.raises(ValueError, match="E1991"):
        assinar_pedido_evento(para_xml_pedido(_pedido()), outro)


def test_certificado_sem_cnpj_e_recusado(xml):
    with pytest.raises(ValueError, match="sem CNPJ"):
        assinar_pedido_evento(xml, _cert(cn="EMPRESA FICTICIA LTDA", cnpj_no_san=None))


def test_chave_que_nao_e_rsa_e_recusada(xml):
    cert = Certificado(
        certificado=gerar_certificado(), chave=ec.generate_private_key(ec.SECP256R1()), cadeia=()
    )
    with pytest.raises(ValueError, match="RSA"):
        assinar_pedido_evento(xml, cert)


def test_entrada_que_nao_e_bytes(xml, cert):
    with pytest.raises(TypeError, match="bytes"):
        assinar_pedido_evento(xml.decode(), cert)


# --- (7) INV-05 e INV-06 -------------------------------------------------------------------


def _pem_da_chave() -> str:
    pem = chave_de_teste().private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return "".join(pem.decode().splitlines()[1:-1])


def test_saida_nao_tem_a_chave(assinado):
    texto = assinado.decode()
    assert _pem_da_chave()[:64] not in texto
    assert "PRIVATE KEY" not in texto


def test_erro_da_biblioteca_e_embrulhado_sem_detalhes(xml, cert, monkeypatch):
    segredo = _pem_da_chave()[:64]

    class Falha:
        def __init__(self, *a, **kw):
            self.namespaces = {}

        def sign(self, *a, **kw):
            raise RuntimeError(f"detalhe interno {segredo}")

    monkeypatch.setattr(assinatura, "XMLSigner", Falha)
    with pytest.raises(ValueError) as erro:
        assinar_pedido_evento(xml, cert)
    assert "falha ao assinar o pedido de evento" in str(erro.value)
    assert segredo not in str(erro.value)
    assert erro.value.__cause__ is None
    assert erro.value.__context__ is None


def test_assinar_nao_escreve_log_nem_saida(xml, cert, caplog, capsys):
    with caplog.at_level(logging.DEBUG):
        conferir_assinatura(assinar_pedido_evento(xml, cert), cert.certificado)
    assert caplog.records == []
    assert capsys.readouterr() == ("", "")


def test_mensagens_de_erro_nao_trazem_a_chave(cert):
    corpo = _pem_da_chave()[:64]
    for entrada in (b"x", f'<pedRegEvento xmlns="{NS}" versao="1.01"/>'.encode()):
        with pytest.raises(ValueError) as erro:
            assinar_pedido_evento(entrada, cert)
        assert corpo not in str(erro.value)
        assert CNPJ not in str(erro.value)


def test_nenhum_campo_do_pedido_tem_default_com_dado_de_emitente():
    from dataclasses import MISSING, fields

    com_default = {f.name for f in fields(PedidoCancelamento) if f.default is not MISSING}
    assert com_default == {"ver_aplic"}


def test_replace_revalida_o_pedido():
    with pytest.raises(ValueError, match="c_motivo"):
        replace(_pedido(), c_motivo=5)
