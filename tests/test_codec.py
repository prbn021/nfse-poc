import base64
import gzip
import random
from pathlib import Path

import pytest

from src.codec import codificar, decodificar

DPS_DE_TESTE = Path(__file__).parent / "dados" / "dps-sem-opcionais.xml"


def _aleatorios(tamanho: int) -> bytes:
    return random.Random(tamanho).randbytes(tamanho)


ENTRADAS = [
    pytest.param(b"", id="vazio"),
    pytest.param(b"<a/>", id="xml-minimo"),
    pytest.param("<a>ação</a>".encode(), id="utf-8"),
    pytest.param(b"\x00\xff" * 10, id="binario"),
    pytest.param(b"x" * 1_000_000, id="repetitivo-1mb"),
    pytest.param(_aleatorios(1), id="aleatorio-1"),
    pytest.param(_aleatorios(4096), id="aleatorio-4k"),
    pytest.param(_aleatorios(300_000), id="aleatorio-300k"),
    pytest.param(DPS_DE_TESTE.read_bytes(), id="dps-de-teste"),
]


@pytest.mark.parametrize("xml", ENTRADAS)
def test_ida_e_volta_devolve_os_mesmos_bytes(xml):
    assert decodificar(codificar(xml)) == xml


@pytest.mark.parametrize("xml", ENTRADAS)
def test_saida_e_base64_de_um_gzip_lido_pela_biblioteca_padrao(xml):
    texto = codificar(xml)
    assert isinstance(texto, str)
    assert gzip.decompress(base64.b64decode(texto, validate=True)) == xml


def test_saida_e_base64_padrao_em_uma_linha():
    texto = codificar(_aleatorios(10_000))
    alfabeto = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")
    assert set(texto) <= alfabeto
    assert len(texto) % 4 == 0


def test_a_mesma_entrada_gera_a_mesma_saida():
    xml = DPS_DE_TESTE.read_bytes()
    assert codificar(xml) == codificar(xml)


def test_decodifica_gzip_gerado_fora_do_modulo():
    xml = "<a>ação</a>".encode()
    texto = base64.b64encode(gzip.compress(xml, compresslevel=1)).decode("ascii")
    assert decodificar(texto) == xml


@pytest.mark.parametrize("entrada", ["<a/>", None, 123, bytearray(b"<a/>")])
def test_codificar_so_aceita_bytes(entrada):
    with pytest.raises(TypeError, match="bytes"):
        codificar(entrada)


@pytest.mark.parametrize("entrada", [b"H4sI", None, 123])
def test_decodificar_so_aceita_texto(entrada):
    with pytest.raises(TypeError, match="str"):
        decodificar(entrada)


@pytest.mark.parametrize(
    "texto",
    [
        pytest.param("não é base64", id="caracteres-fora-do-alfabeto"),
        pytest.param("abc", id="tamanho-errado"),
        pytest.param("H4sI\nAAAA", id="quebra-de-linha"),
        pytest.param("a-b_", id="alfabeto-url-safe"),
        pytest.param("ação", id="nao-ascii"),
    ],
)
def test_texto_que_nao_e_base64_gera_erro_claro(texto):
    with pytest.raises(ValueError, match="não é Base64 válido"):
        decodificar(texto)


def _b64(dados: bytes) -> str:
    return base64.b64encode(dados).decode("ascii")


GZIP_DE_TESTE = gzip.compress(b"<a>conteudo de teste</a>", mtime=0)


@pytest.mark.parametrize(
    "texto",
    [
        pytest.param("", id="vazio"),
        pytest.param(_b64(b"<a/>"), id="xml-sem-gzip"),
        pytest.param(_b64(b"\x1f\x8b"), id="so-o-inicio-do-cabecalho"),
        pytest.param(_b64(GZIP_DE_TESTE[:-5]), id="truncado"),
        pytest.param(
            _b64(GZIP_DE_TESTE[:-8] + b"\x00\x00\x00\x00" + GZIP_DE_TESTE[-4:]), id="crc-errado"
        ),
        pytest.param(
            _b64(GZIP_DE_TESTE[:12] + b"\xff" * 8 + GZIP_DE_TESTE[20:]), id="deflate-corrompido"
        ),
    ],
)
def test_base64_que_nao_e_gzip_gera_erro_claro(texto):
    with pytest.raises(ValueError, match="não é GZip válido"):
        decodificar(texto)


def test_mensagem_de_erro_nao_traz_o_conteudo():
    conteudo = "<a>conteudo-que-nao-deve-aparecer</a>"
    with pytest.raises(ValueError) as erro:
        decodificar(_b64(conteudo.encode()))
    assert "conteudo-que-nao-deve-aparecer" not in str(erro.value)
    assert _b64(conteudo.encode()) not in str(erro.value)
