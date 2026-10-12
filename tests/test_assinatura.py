"""Assinatura XMLDSIG da DPS (T-005, DEC-035). Só certificado autoassinado (DEC-014)."""

import base64
import datetime
import logging
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from lxml import etree
from signxml import SignatureConfiguration, XMLVerifier
from signxml.exceptions import SignXMLException

import src.assinatura as assinatura
from src.assinatura import assinar_dps, conferir_assinatura
from src.certificado import Certificado
from src.config import RAIZ
from src.dps import NS, localizar_xsd_dps, validar_xml
from src.xsd import preparar_copia_local
from tests.pfx import CNPJ, chave_de_teste, gerar_certificado

DS = "http://www.w3.org/2000/09/xmldsig#"
N = {"n": NS, "ds": DS}
EXC_C14N_COM_COMENTARIOS = "http://www.w3.org/2001/10/xml-exc-c14n#WithComments"
ENVELOPED = "http://www.w3.org/2000/09/xmldsig#enveloped-signature"
RSA_SHA256 = "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"
SHA256 = "http://www.w3.org/2001/04/xmlenc#sha256"

# DPS de teste com o prestador de CNPJ igual ao do certificado autoassinado (tests/pfx.py).
DPS = (Path(__file__).parent / "dados" / "dps-sem-opcionais.xml").read_bytes()
ID = etree.fromstring(DPS).find("n:infDPS", N).get("Id")


def _cert(**kw) -> Certificado:
    return Certificado(certificado=gerar_certificado(**kw), chave=chave_de_teste(), cadeia=())


@pytest.fixture(scope="module")
def cert() -> Certificado:
    return _cert()


@pytest.fixture(scope="module")
def assinada(cert) -> bytes:
    return assinar_dps(DPS, cert)


@pytest.fixture(scope="module")
def xsd(tmp_path_factory):
    copia = preparar_copia_local(
        RAIZ / "schemas" / "1.01", tmp_path_factory.mktemp("xsd") / "1.01-local"
    )
    return localizar_xsd_dps(copia)


def _verificar(xml: bytes, cert: Certificado):
    """Verificador independente do módulo: o XMLVerifier do signxml, com o certificado dado."""
    return XMLVerifier().verify(
        xml, x509_cert=cert.certificado, expect_config=SignatureConfiguration(location="./")
    )


# --- (1) e (3): estrutura, XSD e verificação -----------------------------------------------


def test_xml_assinado_e_valido_contra_o_xsd(assinada, xsd):
    assert validar_xml(assinada, xsd) == []


def test_assinatura_e_irma_depois_do_infdps(assinada):
    raiz = etree.fromstring(assinada)
    assert [el.tag for el in raiz] == [f"{{{NS}}}infDPS", f"{{{DS}}}Signature"]


def test_sem_prefixo_de_namespace_e1228(assinada):
    raiz = etree.fromstring(assinada)
    assert all(el.prefix is None for el in raiz.iter())
    assert b"xmlns:" not in assinada


def test_saida_em_utf8_com_declaracao(assinada):
    assert assinada.startswith(b"<?xml version='1.0' encoding='UTF-8'?>")
    assinada.decode("utf-8")


def test_verificador_independente_confirma_e_devolve_o_infdps(assinada, cert):
    resultado = _verificar(assinada, cert)
    assert etree.QName(resultado.signed_xml).localname == "infDPS"
    assert resultado.signed_xml.get("Id") == ID


def test_infdps_nao_muda_ao_assinar(assinada):
    antes = etree.fromstring(DPS).find("n:infDPS", N)
    depois = etree.fromstring(assinada).find("n:infDPS", N)
    assert etree.tostring(depois, method="c14n") == etree.tostring(antes, method="c14n")


@pytest.mark.parametrize(
    ("de", "para"),
    [
        (b"<vServ>100.00<", b"<vServ>100.01<"),
        (b"<xNome>Cliente<", b"<xNome>Clienta<"),
        (b'Id="DPS3304557', b'Id="DPS3304558'),
        (b"<tpAmb>2</tpAmb>", b"<tpAmb>2</tpAmb><!-- x -->"),
    ],
)
def test_alterar_o_infdps_invalida_a_assinatura(assinada, cert, de, para):
    adulterada = assinada.replace(de, para, 1)
    assert adulterada != assinada
    with pytest.raises(SignXMLException):
        _verificar(adulterada, cert)


def test_alterar_o_texto_de_qualquer_elemento_do_infdps_invalida(assinada, cert):
    raiz = etree.fromstring(assinada)
    textos = [el for el in raiz.find("n:infDPS", N).iter() if el.text and el.text.strip()]
    assert textos
    for el in textos:
        copia = etree.fromstring(assinada)
        alvo = copia.xpath(etree.ElementTree(raiz).getpath(el))[0]
        alvo.text = alvo.text[:-1] + ("X" if alvo.text[-1] != "X" else "Y")
        with pytest.raises(SignXMLException):
            _verificar(etree.tostring(copia, xml_declaration=True, encoding="UTF-8"), cert)


def test_mesma_entrada_gera_a_mesma_saida(assinada, cert):
    # RSA PKCS#1 v1.5 é determinístico.
    assert assinar_dps(DPS, cert) == assinada


# --- (2): perfil --------------------------------------------------------------------------


def _attr(raiz, caminho: str) -> list[str]:
    return [el.get("Algorithm") for el in raiz.findall(caminho, N)]


def test_perfil_igual_ao_da_nfse_devolvida(assinada):
    sig = etree.fromstring(assinada).find("ds:Signature", N)
    assert _attr(sig, "ds:SignedInfo/ds:CanonicalizationMethod") == [EXC_C14N_COM_COMENTARIOS]
    assert _attr(sig, "ds:SignedInfo/ds:SignatureMethod") == [RSA_SHA256]
    referencias = sig.findall("ds:SignedInfo/ds:Reference", N)
    assert [r.get("URI") for r in referencias] == [f"#{ID}"]
    assert _attr(referencias[0], "ds:Transforms/ds:Transform") == [
        ENVELOPED,
        EXC_C14N_COM_COMENTARIOS,
    ]
    assert _attr(referencias[0], "ds:DigestMethod") == [SHA256]


def test_keyinfo_so_com_o_certificado_do_emitente(assinada, cert):
    key_info = etree.fromstring(assinada).find("ds:Signature/ds:KeyInfo", N)
    assert [etree.QName(el).localname for el in key_info] == ["X509Data"]
    certificados = key_info.findall("ds:X509Data/ds:X509Certificate", N)
    assert len(certificados) == 1
    der = cert.certificado.public_bytes(serialization.Encoding.DER)
    assert base64.b64decode("".join(certificados[0].text.split())) == der


def test_conferir_assinatura_aceita_a_dps_assinada(assinada, cert):
    conferir_assinatura(assinada, cert.certificado)


def test_conferir_assinatura_recusa_dps_adulterada(assinada, cert):
    with pytest.raises(ValueError, match="assinatura inválida"):
        conferir_assinatura(assinada.replace(b">100.00<", b">100.01<", 1), cert.certificado)


def test_conferir_assinatura_recusa_certificado_de_outra_chave(assinada):
    # Mesmo titular e CNPJ, outra chave: a conferência tem de falhar.
    outra_chave = ec.generate_private_key(ec.SECP256R1())
    certificado = (
        x509.CertificateBuilder()
        .subject_name(gerar_certificado().subject)
        .issuer_name(gerar_certificado().subject)
        .public_key(outra_chave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC))
        .not_valid_after(datetime.datetime(2036, 1, 1, tzinfo=datetime.UTC))
        .sign(outra_chave, hashes.SHA256())
    )
    with pytest.raises(ValueError, match="assinatura inválida"):
        conferir_assinatura(assinada, certificado)


def test_conferir_assinatura_recusa_dps_sem_assinatura(cert):
    with pytest.raises(ValueError, match="assinatura inválida"):
        conferir_assinatura(DPS, cert.certificado)


# --- (4): casos negativos ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("xml", "trecho"),
    [
        (b"isto nao e xml", "não é XML"),
        (b"", "não é XML"),
        (f'<outra xmlns="{NS}"/>'.encode(), "raiz não é DPS"),
        (b'<DPS versao="1.01"/>', "raiz não é DPS"),
        (f'<DPS xmlns="{NS}" versao="1.01"/>'.encode(), "sem infDPS"),
        (f'<DPS xmlns="{NS}" versao="1.01"><infDPS/></DPS>'.encode(), "infDPS sem Id"),
    ],
)
def test_xml_fora_do_formato_gera_erro_claro(cert, xml, trecho):
    with pytest.raises(ValueError, match=trecho):
        assinar_dps(xml, cert)


def test_dps_ja_assinada_e_recusada(assinada, cert):
    with pytest.raises(ValueError, match="já está assinada"):
        assinar_dps(assinada, cert)


def test_certificado_de_outro_cnpj_e_recusado_e0718():
    outro = _cert(cn="OUTRA EMPRESA FICTICIA:99888777000161", cnpj_no_san="99888777000161")
    with pytest.raises(ValueError, match="E0718"):
        assinar_dps(DPS, outro)


def test_certificado_sem_cnpj_e_recusado():
    sem_cnpj = _cert(cn="EMPRESA FICTICIA LTDA", cnpj_no_san=None)
    with pytest.raises(ValueError, match="sem CNPJ"):
        assinar_dps(DPS, sem_cnpj)


def test_chave_que_nao_e_rsa_e_recusada():
    chave = ec.generate_private_key(ec.SECP256R1())
    cert = Certificado(certificado=gerar_certificado(), chave=chave, cadeia=())
    with pytest.raises(ValueError, match="RSA"):
        assinar_dps(DPS, cert)


def test_entrada_que_nao_e_bytes(cert):
    with pytest.raises(TypeError, match="bytes"):
        assinar_dps(DPS.decode(), cert)


# --- (5): INV-05 ---------------------------------------------------------------------------


def _pem_da_chave() -> str:
    pem = chave_de_teste().private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return "".join(pem.decode().splitlines()[1:-1])


def test_saida_nao_tem_a_chave(assinada):
    corpo = _pem_da_chave()
    texto = assinada.decode()
    assert corpo[:64] not in texto
    assert "PRIVATE KEY" not in texto


def test_erro_da_biblioteca_e_embrulhado_sem_detalhes(cert, monkeypatch):
    segredo = _pem_da_chave()[:64]

    class Falha:
        def __init__(self, *a, **kw):
            self.namespaces = {}

        def sign(self, *a, **kw):
            raise RuntimeError(f"detalhe interno {segredo}")

    monkeypatch.setattr(assinatura, "XMLSigner", Falha)
    with pytest.raises(ValueError) as erro:
        assinar_dps(DPS, cert)
    assert "falha ao assinar a DPS" in str(erro.value)
    assert segredo not in str(erro.value)
    # Nada da exceção original fica encadeado, nem em traceback.
    assert erro.value.__cause__ is None
    assert erro.value.__context__ is None


def test_assinar_nao_escreve_log_nem_saida(cert, caplog, capsys):
    with caplog.at_level(logging.DEBUG):
        assinar_dps(DPS, cert)
        conferir_assinatura(assinar_dps(DPS, cert), cert.certificado)
    assert caplog.records == []
    assert capsys.readouterr() == ("", "")


def test_mensagens_de_erro_nao_trazem_a_chave(cert):
    corpo = _pem_da_chave()[:64]
    for xml in (b"x", f'<DPS xmlns="{NS}" versao="1.01"/>'.encode()):
        with pytest.raises(ValueError) as erro:
            assinar_dps(xml, cert)
        assert corpo not in str(erro.value)
        assert CNPJ not in str(erro.value)
