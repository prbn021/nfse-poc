"""Carga do certificado A1 (T-004). Só PFX autoassinado gerado aqui, nunca o de um cliente."""

import datetime
import logging

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from src.certificado import Certificado, carregar_certificado
from tests.pfx import (
    CNPJ,
    OCTET_STRING,
    PRINTABLE_STRING,
    TITULAR,
    UTF8_STRING,
    chave_de_teste,
    gerar_pfx,
)

SENHA = "s3nh4-f1ct1c14-xyz"
SENHA_ERRADA = "0utr4-s3nh4-qwe"


def gravar(pasta, dados: bytes, nome="acme.pfx"):
    arquivo = pasta / nome
    arquivo.write_bytes(dados)
    return arquivo


@pytest.fixture
def pfx(tmp_path):
    return gravar(tmp_path, gerar_pfx(SENHA))


def test_carrega_certificado_e_chave(pfx):
    cert = carregar_certificado(pfx, SENHA)
    assert isinstance(cert, Certificado)
    assert isinstance(cert.chave, rsa.RSAPrivateKey)
    # A chave devolvida é a par do certificado.
    assert (
        cert.chave.public_key().public_numbers() == cert.certificado.public_key().public_numbers()
    )
    assert cert.chave.private_numbers() == chave_de_teste().private_numbers()
    assert cert.cadeia == ()


def test_expoe_titular_cnpj_e_validade(tmp_path):
    inicio = datetime.datetime(2026, 1, 2, 3, 4, 5, tzinfo=datetime.UTC)
    cert = carregar_certificado(gravar(tmp_path, gerar_pfx(SENHA, inicio=inicio, dias=10)), SENHA)
    assert cert.titular == TITULAR
    assert cert.cnpj == CNPJ
    assert cert.valido_de == inicio
    assert cert.valido_ate == inicio + datetime.timedelta(days=10)


def test_pfx_sem_senha(tmp_path):
    cert = carregar_certificado(gravar(tmp_path, gerar_pfx("")), "")
    assert cert.cnpj == CNPJ


def test_nao_recusa_certificado_vencido(tmp_path):
    # Carregar não julga a validade: o script mostra as datas, e quem conecta decide.
    inicio = datetime.datetime(2020, 1, 1, tzinfo=datetime.UTC)
    cert = carregar_certificado(gravar(tmp_path, gerar_pfx(SENHA, inicio=inicio, dias=1)), SENHA)
    assert cert.valido_ate < datetime.datetime.now(datetime.UTC)


# --- CNPJ do titular ----------------------------------------------------------------------


@pytest.mark.parametrize("tag", [OCTET_STRING, PRINTABLE_STRING, UTF8_STRING])
def test_cnpj_vem_do_other_name_do_san(tmp_path, tag):
    dados = gerar_pfx(
        SENHA, cn="EMPRESA FICTICIA LTDA", cnpj_no_san="99888777000161", tag_do_san=tag
    )
    assert carregar_certificado(gravar(tmp_path, dados), SENHA).cnpj == "99888777000161"


def test_other_name_tem_precedencia_sobre_o_cn(tmp_path):
    dados = gerar_pfx(
        SENHA, cn="EMPRESA FICTICIA LTDA:11222333000181", cnpj_no_san="99888777000161"
    )
    assert carregar_certificado(gravar(tmp_path, dados), SENHA).cnpj == "99888777000161"


def test_sem_other_name_o_cnpj_vem_do_fim_do_cn(tmp_path):
    dados = gerar_pfx(SENHA, cn="EMPRESA FICTICIA LTDA:99888777000161", cnpj_no_san=None)
    assert carregar_certificado(gravar(tmp_path, dados), SENHA).cnpj == "99888777000161"


@pytest.mark.parametrize(
    ("cn", "cnpj_no_san"),
    [
        ("EMPRESA FICTICIA LTDA", None),
        ("FULANO DE TAL:12345678901", None),  # 11 dígitos: CPF, não CNPJ
        ("EMPRESA FICTICIA LTDA", "1122233300018"),  # 13 dígitos
        ("EMPRESA FICTICIA LTDA", "1122233300018X"),
        (None, None),
    ],
)
def test_cnpj_ausente_e_none(tmp_path, cn, cnpj_no_san):
    dados = gerar_pfx(SENHA, cn=cn, cnpj_no_san=cnpj_no_san)
    assert carregar_certificado(gravar(tmp_path, dados), SENHA).cnpj is None


def test_sem_cn_o_titular_e_o_nome_completo(tmp_path):
    cert = carregar_certificado(gravar(tmp_path, gerar_pfx(SENHA, cn=None)), SENHA)
    assert cert.titular == "C=BR"


# --- erros --------------------------------------------------------------------------------


def test_arquivo_ausente(tmp_path):
    with pytest.raises(ValueError, match="certificado não encontrado") as erro:
        carregar_certificado(tmp_path / "nao-existe.pfx", SENHA)
    assert "nao-existe.pfx" in str(erro.value)


def test_caminho_que_e_pasta(tmp_path):
    with pytest.raises(ValueError, match="certificado não encontrado"):
        carregar_certificado(tmp_path, SENHA)


@pytest.mark.parametrize("senha", [SENHA_ERRADA, "", SENHA + " ", SENHA.upper()])
def test_senha_errada(pfx, senha):
    with pytest.raises(ValueError, match="senha incorreta") as erro:
        carregar_certificado(pfx, senha)
    assert "acme.pfx" in str(erro.value)


@pytest.mark.parametrize(
    "dados",
    [
        b"",
        b"isto nao e um certificado",
        b"-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n",
        b"\x30\x03\x02\x01\x01",  # SEQUENCE DER que não é PFX (versão 1)
        b"\x30",
    ],
)
def test_arquivo_que_nao_e_pfx(tmp_path, dados):
    with pytest.raises(ValueError, match="não é um arquivo PFX") as erro:
        carregar_certificado(gravar(tmp_path, dados), SENHA)
    assert "acme.pfx" in str(erro.value)


def test_pfx_truncado(tmp_path):
    with pytest.raises(ValueError, match="senha incorreta ou PFX corrompido"):
        carregar_certificado(gravar(tmp_path, gerar_pfx(SENHA)[:300]), SENHA)


def test_pfx_sem_chave_privada(tmp_path):
    with pytest.raises(ValueError, match="PFX sem chave privada"):
        carregar_certificado(gravar(tmp_path, gerar_pfx(SENHA, com_chave=False)), SENHA)


def test_pfx_sem_certificado(tmp_path):
    with pytest.raises(ValueError, match="PFX sem certificado"):
        carregar_certificado(gravar(tmp_path, gerar_pfx(SENHA, com_certificado=False)), SENHA)


# --- INV-05: senha e chave nunca aparecem em repr, mensagem de erro ou log -----------------


def _segredos_da_chave() -> list[str]:
    chave = chave_de_teste()
    numeros = chave.private_numbers()
    pem = chave.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")
    return [
        str(numeros.d),
        f"{numeros.d:x}",
        str(numeros.p),
        f"{numeros.p:x}",
        pem.splitlines()[1],
        "PRIVATE KEY",
    ]


def test_repr_mostra_so_titular_cnpj_e_validade(pfx):
    cert = carregar_certificado(pfx, SENHA)
    for texto in (repr(cert), str(cert), f"{cert}", repr([cert])):
        assert TITULAR in texto
        assert "valido_ate" in texto
        assert SENHA not in texto
        assert "chave" not in texto
        for segredo in _segredos_da_chave():
            assert segredo not in texto


def test_o_certificado_nao_guarda_a_senha(pfx):
    cert = carregar_certificado(pfx, SENHA)
    assert SENHA not in repr(vars(cert))
    assert all(valor != SENHA for valor in vars(cert).values())


@pytest.mark.parametrize(
    ("dados", "senha"),
    [
        (gerar_pfx(SENHA), SENHA_ERRADA),
        (gerar_pfx(SENHA)[:300], SENHA),
        (b"isto nao e um certificado", SENHA),
        (SENHA.encode(), SENHA),  # a senha gravada no lugar do certificado
        (gerar_pfx(SENHA, com_chave=False), SENHA),
        (gerar_pfx(SENHA, com_certificado=False), SENHA),
        (None, SENHA),  # arquivo ausente
    ],
    ids=range(7),
)
def test_senha_nao_aparece_em_mensagem_de_erro_nem_em_log(tmp_path, caplog, capsys, dados, senha):
    arquivo = tmp_path / "acme.pfx"
    if dados is not None:
        arquivo.write_bytes(dados)
    with caplog.at_level(logging.DEBUG), pytest.raises(ValueError) as erro:
        carregar_certificado(arquivo, senha)
    saida = capsys.readouterr()
    for texto in (str(erro.value), repr(erro.value), caplog.text, saida.out, saida.err):
        assert SENHA not in texto
        assert SENHA_ERRADA not in texto
    # A exceção da biblioteca não fica encadeada.
    assert erro.value.__cause__ is None
    assert erro.value.__context__ is None


def test_carga_bem_sucedida_nao_escreve_log_nem_saida(pfx, caplog, capsys):
    with caplog.at_level(logging.DEBUG):
        carregar_certificado(pfx, SENHA)
    saida = capsys.readouterr()
    assert caplog.records == []
    assert saida.out == ""
    assert saida.err == ""
