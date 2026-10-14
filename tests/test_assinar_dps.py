"""O script manual assina a DPS de exemplo, confere a assinatura e empacota em GZip+Base64.

T-005, critério do M2 (DEC-035). Só certificado autoassinado (DEC-014).
"""

import sys

import pytest
from signxml import SignatureConfiguration, XMLVerifier

from src.codec import decodificar
from src.config import RAIZ, XSD_DIR_PADRAO
from src.dps import localizar_xsd_dps, validar_xml
from tests.pfx import CNPJ, gerar_certificado, gerar_pfx

sys.path.insert(0, str(RAIZ / "scripts"))

import assinar_dps

SENHA = "s3nh4-f1ct1c14-abc"


def emitente(pasta, *, senha=SENHA, cnpj=CNPJ, nome="acme"):
    """Grava um PFX autoassinado e o arquivo do emitente fictício que aponta para ele."""
    (pasta / f"{nome}.pfx").write_bytes(gerar_pfx(SENHA))
    (pasta / f"{nome}.toml").write_text(
        f'cnpj = "{cnpj}"\nmunicipio = "3304557"\nop_simp_nac = 3\n'
        "reg_ap_trib_sn = 1\nreg_esp_trib = 0\n\n"
        f'[certificado]\ncaminho = "{(pasta / nome).as_posix()}.pfx"\nsenha = "{senha}"\n',
        encoding="utf-8",
    )
    return pasta


@pytest.fixture
def pastas(tmp_path):
    emitentes = tmp_path / "emitentes"
    emitentes.mkdir()
    return emitente(emitentes), tmp_path / "out"


def test_dps_de_exemplo_sai_assinada_e_em_gzip_base64(pastas, capsys):
    emitentes, saida = pastas
    assert assinar_dps.main(["--emitente", "acme"], pasta=emitentes, saida=saida) == 0

    [xml_arq] = saida.glob("*-assinada.xml")
    [b64_arq] = saida.glob("*-assinada.b64")
    xml = xml_arq.read_bytes()
    assert decodificar(b64_arq.read_text(encoding="ascii")) == xml

    # Conferência independente do script: XSD e assinatura com o certificado de teste.
    xsd = localizar_xsd_dps(XSD_DIR_PADRAO)
    assert validar_xml(xml, xsd) == []
    resultado = XMLVerifier().verify(
        xml, x509_cert=gerar_certificado(), expect_config=SignatureConfiguration(location="./")
    )
    assert resultado.signed_xml.get("Id") == xml_arq.name.removesuffix("-assinada.xml")

    out, err = capsys.readouterr()
    assert err == ""
    assert "[OK] Assinatura conferida" in out
    assert "[OK] Válida contra" in out
    assert SENHA not in out
    assert "PRIVATE KEY" not in out


def test_senha_errada_sai_com_erro_sem_mostrar_a_senha(tmp_path, capsys):
    emitentes = emitente(tmp_path, senha="0utr4-s3nh4-qwe")
    assert assinar_dps.main(["--emitente", "acme"], pasta=emitentes, saida=tmp_path / "o") == 1
    out, err = capsys.readouterr()
    assert out == ""
    assert "senha incorreta" in err
    assert "0utr4-s3nh4-qwe" not in err
    assert SENHA not in err
    assert not (tmp_path / "o").exists()


def test_certificado_de_outro_cnpj_sai_com_erro_e0718(tmp_path, capsys):
    emitentes = emitente(tmp_path, cnpj="99888777000161")
    assert assinar_dps.main(["--emitente", "acme"], pasta=emitentes, saida=tmp_path / "o") == 1
    assert "E0718" in capsys.readouterr().err
    assert not (tmp_path / "o").exists()


def test_emitente_e_obrigatorio(capsys):
    with pytest.raises(SystemExit) as saida:
        assinar_dps.main([])
    assert saida.value.code == 2
    assert "--emitente" in capsys.readouterr().err


def test_o_emitente_de_exemplo_nao_tem_certificado(tmp_path, capsys):
    assert assinar_dps.main(["--emitente", "exemplo"], saida=tmp_path / "o") == 1
    assert "certificado não encontrado" in capsys.readouterr().err
