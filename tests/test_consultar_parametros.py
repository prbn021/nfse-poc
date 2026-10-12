"""Script manual de consulta da parametrização municipal no ADN (T-026). Sem rede: o ADN é
simulado com `httpx.MockTransport`; o certificado é o autoassinado de tests/pfx.py.
"""

import json
import sys
from pathlib import Path

import httpx
import pytest

from src.config import RAIZ, Config
from tests.pfx import CNPJ, gerar_pfx

sys.path.insert(0, str(RAIZ / "scripts"))

import consultar_parametros

SENHA = "s3nh4-f1ct1c14-prm"
ADN = "https://adn.producaorestrita.nfse.gov.br"
CONVENIO = {
    "mensagem": None,
    "parametrosConvenio": {
        "tipoConvenioDeserializationSetter": 1,
        "aderenteAmbienteNacional": 1,
        "aderenteEmissorNacional": 1,
        "aderenteMAN": 0,
    },
}
# Fictício: 990101 não é um código real da lista nacional.
ALIQUOTAS = {
    "Mensagem": None,
    "Aliquotas": {
        "990101000": [
            {"Incidencia": "1", "Aliq": 5.0, "DtIni": "2025-01-01T00:00:00", "DtFim": None}
        ]
    },
}


def config(adn_url=ADN) -> Config:
    return Config("homologacao", "https://sefin.producaorestrita.nfse.gov.br/x", adn_url, Path("x"))


@pytest.fixture
def emitentes(tmp_path):
    pasta = tmp_path / "emitentes"
    pasta.mkdir()
    (pasta / "acme.pfx").write_bytes(gerar_pfx(SENHA))
    (pasta / "acme.toml").write_text(
        f'cnpj = "{CNPJ}"\nmunicipio = "3304557"\nop_simp_nac = 3\n'
        "reg_ap_trib_sn = 1\nreg_esp_trib = 0\n\n"
        f'[certificado]\ncaminho = "{(pasta / "acme").as_posix()}.pfx"\nsenha = "{SENHA}"\n',
        encoding="utf-8",
    )
    return pasta


def adn(pedidos, *, respostas):
    """ADN simulado: `respostas` mapeia o caminho depois de /parametrizacao/ para a resposta."""

    def responder(pedido: httpx.Request) -> httpx.Response:
        pedidos.append(pedido.url.path)
        caminho = pedido.url.path.removeprefix("/parametrizacao/")
        resposta = respostas.get(caminho)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta or httpx.Response(404, json={"mensagem": "não encontrado (simulado)"})

    return httpx.MockTransport(responder)


def rodar(emitentes, tmp_path, transporte, *args, cfg=None):
    return consultar_parametros.main(
        ["--emitente", "acme", "--c-trib-nac", "990101", *args],
        pasta=emitentes,
        config=cfg or config(),
        transporte=transporte,
        saida=tmp_path / "out",
    )


def test_consulta_convenio_e_historico_com_9_e_6_digitos(emitentes, tmp_path, capsys):
    pedidos = []
    respostas = {
        "3304557/convenio": httpx.Response(200, json=CONVENIO),
        "3304557/990101000/historicoaliquotas": httpx.Response(200, json=ALIQUOTAS),
    }
    assert rodar(emitentes, tmp_path, adn(pedidos, respostas=respostas)) == 0
    assert pedidos == [
        "/parametrizacao/3304557/convenio",
        "/parametrizacao/3304557/990101000/historicoaliquotas",
        "/parametrizacao/3304557/990101/historicoaliquotas",
    ]
    out, err = capsys.readouterr()
    assert err == ""
    assert f"ADN: {ADN}" in out
    assert "Convênio de 3304557: HTTP 200" in out
    assert "aderenteEmissorNacional=1" in out
    assert "Histórico de alíquotas de 990101000: HTTP 200" in out
    assert "990101000: Incidencia=1, Aliq=5.0, DtIni=2025-01-01T00:00:00, DtFim=None" in out
    assert "Histórico de alíquotas de 990101: HTTP 404 (não encontrado (simulado))" in out
    assert SENHA not in out
    assert CNPJ not in out

    saida = tmp_path / "out"
    assert json.loads((saida / "adn-3304557-convenio.json").read_text()) == CONVENIO
    historico = saida / "adn-3304557-990101000-historicoaliquotas.json"
    assert json.loads(historico.read_text()) == ALIQUOTAS
    assert (saida / "adn-3304557-990101-historicoaliquotas.json").exists()


def test_municipio_pode_ser_outro_que_o_do_emitente(emitentes, tmp_path, capsys):
    pedidos = []
    assert rodar(emitentes, tmp_path, adn(pedidos, respostas={}), "--municipio", "3550308") == 0
    assert all(p.startswith("/parametrizacao/3550308/") for p in pedidos)
    assert "Convênio de 3550308: HTTP 404" in capsys.readouterr().out


def test_erro_de_rede_sai_com_codigo_3(emitentes, tmp_path, capsys):
    transporte = adn([], respostas={"3304557/convenio": httpx.ConnectError("simulado")})
    assert rodar(emitentes, tmp_path, transporte) == consultar_parametros.ERRO_DE_REDE
    assert "erro de conexão" in capsys.readouterr().err


def test_resposta_inesperada_e_salva(emitentes, tmp_path, capsys):
    respostas = {"3304557/convenio": httpx.Response(500, content=b"falha interna")}
    transporte = adn([], respostas=respostas)
    assert rodar(emitentes, tmp_path, transporte) == consultar_parametros.RESPOSTA_INESPERADA
    assert (tmp_path / "out" / "adn-3304557-convenio.json").read_bytes() == b"falha interna"
    assert "falha interna" not in capsys.readouterr().err


def test_adn_fora_da_producao_restrita_e_recusado(emitentes, tmp_path, capsys):
    pedidos = []
    cfg = config("https://adn.nfse.gov.br")
    assert rodar(emitentes, tmp_path, adn(pedidos, respostas={}), cfg=cfg) == 1
    assert pedidos == []
    assert "INV-02" in capsys.readouterr().err


@pytest.mark.parametrize("args", [["--c-trib-nac", "12"], ["--municipio", "123"]])
def test_codigos_fora_do_formato(emitentes, tmp_path, capsys, args):
    pedidos = []
    argv = ["--emitente", "acme", "--c-trib-nac", "990101", *args]
    codigo = consultar_parametros.main(
        argv,
        pasta=emitentes,
        config=config(),
        transporte=adn(pedidos, respostas={}),
        saida=tmp_path / "out",
    )
    assert codigo == 1
    assert pedidos == []


@pytest.mark.parametrize("argv", [[], ["--emitente", "acme"], ["--c-trib-nac", "990101"]])
def test_emitente_e_codigo_sao_obrigatorios(argv):
    with pytest.raises(SystemExit) as saida:
        consultar_parametros.main(argv)
    assert saida.value.code == 2
