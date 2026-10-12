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


def test_consulta_convenio_e_historico_com_9_digitos_e_pontuado(emitentes, tmp_path, capsys):
    pedidos = []
    respostas = {
        "3304557/convenio": httpx.Response(200, json=CONVENIO),
        "3304557/990101000/historicoaliquotas": httpx.Response(200, json=ALIQUOTAS),
    }
    assert rodar(emitentes, tmp_path, adn(pedidos, respostas=respostas)) == 0
    # 6 dígitos foi recusado pela API real; vão 9 dígitos e o formato pontuado (DEC-041).
    assert pedidos == [
        "/parametrizacao/3304557/convenio",
        "/parametrizacao/3304557/990101000/historicoaliquotas",
        "/parametrizacao/3304557/99.01.01.000/historicoaliquotas",
    ]
    out, err = capsys.readouterr()
    assert err == ""
    assert f"ADN: {ADN}" in out
    assert "Convênio de 3304557: HTTP 200" in out
    assert "aderenteEmissorNacional=1" in out
    assert "Histórico de alíquotas de 990101000: HTTP 200" in out
    assert "990101000: Incidencia=1, Aliq=5.0, DtIni=2025-01-01T00:00:00, DtFim=None" in out
    assert "Histórico de alíquotas de 99.01.01.000: HTTP 404 (não encontrado (simulado))" in out
    assert SENHA not in out
    assert CNPJ not in out

    saida = tmp_path / "out"
    assert json.loads((saida / "adn-3304557-convenio.json").read_text()) == CONVENIO
    historico = saida / "adn-3304557-990101000-historicoaliquotas.json"
    assert json.loads(historico.read_text()) == ALIQUOTAS
    assert (saida / "adn-3304557-99.01.01.000-historicoaliquotas.json").exists()


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


# --- varredura da lista nacional (T-026, DEC-042) -----------------------------------------

LISTA_FICTICIA = [
    ("990101", "Serviço fictício A."),
    ("990102", "Serviço fictício B."),
    ("990103", "Serviço fictício C."),
]


def rodar_varredura(emitentes, tmp_path, transporte, monkeypatch, *args):
    monkeypatch.setattr(consultar_parametros, "servicos_nacionais", lambda _: LISTA_FICTICIA)
    return consultar_parametros.main(
        ["--emitente", "acme", "--varrer", *args],
        pasta=emitentes,
        config=config(),
        transporte=transporte,
        saida=tmp_path / "out",
    )


def test_varredura_lista_os_codigos_com_aliquota(emitentes, tmp_path, capsys, monkeypatch):
    pedidos = []
    respostas = {
        "3304557/convenio": httpx.Response(200, json=CONVENIO),
        "3304557/99.01.02.000/historicoaliquotas": httpx.Response(
            200,
            json={
                "mensagem": None,
                "aliquotas": {"99.01.02.000": [{"Aliq": 2.0, "DtIni": "2025-01-01T00:00:00"}]},
            },
        ),
        "3304557/99.01.03.000/historicoaliquotas": httpx.Response(
            400, json={"mensagem": "Chamada mal formada."}
        ),
    }
    assert rodar_varredura(emitentes, tmp_path, adn(pedidos, respostas=respostas), monkeypatch) == 0
    assert pedidos == [
        "/parametrizacao/3304557/convenio",
        "/parametrizacao/3304557/99.01.01.000/historicoaliquotas",
        "/parametrizacao/3304557/99.01.02.000/historicoaliquotas",
        "/parametrizacao/3304557/99.01.03.000/historicoaliquotas",
    ]
    out = capsys.readouterr().out
    assert (
        "Varredura de 3 códigos em 3304557: 1 com alíquota, 1 sem (404), 1 com outro status" in out
    )
    assert "990102 Serviço fictício B.: Aliq=2.0, DtIni=2025-01-01T00:00:00" in out
    assert "990103: HTTP 400 (Chamada mal formada.)" in out

    resumo = json.loads((tmp_path / "out" / "adn-3304557-varredura.json").read_text("utf-8"))
    assert [item["codigo"] for item in resumo] == ["990101", "990102", "990103"]
    assert [item["status"] for item in resumo] == [404, 200, 400]
    assert resumo[1]["aliquotas"] == {
        "99.01.02.000": [{"Aliq": 2.0, "DtIni": "2025-01-01T00:00:00"}]
    }


def test_varredura_sem_nenhum_codigo(emitentes, tmp_path, capsys, monkeypatch):
    assert rodar_varredura(emitentes, tmp_path, adn([], respostas={}), monkeypatch) == 0
    assert "nenhum código com alíquota" in capsys.readouterr().out


def test_varredura_para_no_erro_de_rede(emitentes, tmp_path, capsys, monkeypatch):
    respostas = {
        "3304557/convenio": httpx.Response(200, json=CONVENIO),
        "3304557/99.01.02.000/historicoaliquotas": httpx.ConnectError("simulado"),
    }
    transporte = adn([], respostas=respostas)
    codigo = rodar_varredura(emitentes, tmp_path, transporte, monkeypatch)
    assert codigo == consultar_parametros.ERRO_DE_REDE
    assert "erro de conexão" in capsys.readouterr().err


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["--emitente", "acme"],
        ["--c-trib-nac", "990101"],
        ["--emitente", "acme", "--c-trib-nac", "990101", "--varrer"],
    ],
)
def test_emitente_e_codigo_sao_obrigatorios(argv):
    with pytest.raises(SystemExit) as saida:
        consultar_parametros.main(argv)
    assert saida.value.code == 2
