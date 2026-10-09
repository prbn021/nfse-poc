"""Script manual do teste de conexão (T-015). O servidor é simulado com httpx.MockTransport."""

import json
import sys
from pathlib import Path

import httpx
import pytest

from src.config import RAIZ, Config
from tests.pfx import gerar_pfx

sys.path.insert(0, str(RAIZ / "scripts"))

import testar_conexao

SENHA = "s3nh4-f1ct1c14-xyz"
BASE = "https://sefin.producaorestrita.nfse.gov.br/SefinNacional"
PAGINA = (
    b'<html><script>var c = {"urls":[{"url":"/SefinNacional/docs/v1/swagger.json",'
    b'"name":"v1"}]};</script></html>'
)
OPENAPI = {
    "openapi": "3.0.1",
    "servers": [{"url": BASE}],
    "paths": {"/nfse": {}, "/dps/{id}": {}},
}


def config(sefin_url=BASE) -> Config:
    return Config("homologacao", sefin_url, "https://adn.producaorestrita.nfse.gov.br", Path("x"))


def emitente(pasta: Path, nome="acme") -> Path:
    (pasta / f"{nome}.pfx").write_bytes(gerar_pfx(SENHA))
    (pasta / f"{nome}.toml").write_text(
        'cnpj = "11222333000181"\nmunicipio = "3304557"\nop_simp_nac = 3\nreg_esp_trib = 0\n\n'
        f'[certificado]\ncaminho = "{(pasta / nome).as_posix()}.pfx"\nsenha = "{SENHA}"\n',
        encoding="utf-8",
    )
    return pasta


def servidor(pedidos: list, *, pagina=PAGINA, falha: Exception | None = None):
    def responder(pedido: httpx.Request) -> httpx.Response:
        pedidos.append((pedido.method, str(pedido.url)))
        if falha is not None:
            raise falha
        caminho = pedido.url.path
        if caminho == "/SefinNacional/docs/index":
            return httpx.Response(200, headers={"content-type": "text/html"}, content=pagina)
        if caminho == "/SefinNacional/docs/v1/swagger.json":
            return httpx.Response(200, json=OPENAPI)
        return httpx.Response(404)

    return httpx.MockTransport(responder)


def rodar(tmp_path, transporte, *, cfg=None, nome="acme"):
    pasta = tmp_path / "emitentes"
    pasta.mkdir(exist_ok=True)
    emitente(pasta)
    return testar_conexao.main(
        ["--emitente", nome],
        pasta=pasta,
        config=cfg or config(),
        transporte=transporte,
        saida=tmp_path / "out",
    )


def test_consulta_documentacao_openapi_e_dps(tmp_path, capsys):
    pedidos = []
    assert rodar(tmp_path, servidor(pedidos)) == 0
    assert [metodo for metodo, _ in pedidos] == ["GET", "GET", "HEAD"]
    assert pedidos[0][1] == f"{BASE}/docs/index"
    assert pedidos[1][1] == f"{BASE}/docs/v1/swagger.json"
    assert pedidos[2][1].startswith(f"{BASE}/dps/DPS")

    saida = capsys.readouterr()
    assert saida.err == ""
    linhas = saida.out.splitlines()
    assert linhas[0] == f"SEFIN: {BASE}"
    assert linhas[1].startswith("GET docs/index: 200 (text/html, ")
    assert linhas[2].startswith("GET docs/v1/swagger.json: 200 (application/json, ")
    assert f"servers: {BASE}" in linhas
    assert "rotas: /dps/{id}, /nfse" in linhas
    assert linhas[-1] == "HEAD dps/<Id que não existe>: 404"

    assert (tmp_path / "out" / "sefin-docs-index.html").read_bytes() == PAGINA
    assert json.loads((tmp_path / "out" / "sefin-openapi.json").read_text()) == OPENAPI


def test_a_saida_nao_tem_senha_nem_id_da_dps(tmp_path, capsys):
    rodar(tmp_path, servidor([]))
    saida = capsys.readouterr()
    assert SENHA not in saida.out + saida.err
    assert "PRIVATE KEY" not in saida.out + saida.err
    assert "11222333000181" not in saida.out + saida.err


def test_segue_o_link_openapi_do_redoc(tmp_path, capsys):
    # Formato da página real da SEFIN (ReDoc), com URL fictícia.
    pagina = b"initTry({\n    openApi: '" + BASE.encode() + b"/docs/v1/swagger.json',\n})"
    pedidos = []
    assert rodar(tmp_path, servidor(pedidos, pagina=pagina)) == 0
    assert pedidos[1] == ("GET", f"{BASE}/docs/v1/swagger.json")
    assert "rotas: /dps/{id}, /nfse" in capsys.readouterr().out


def test_pagina_sem_link_para_a_especificacao(tmp_path, capsys):
    pedidos = []
    assert rodar(tmp_path, servidor(pedidos, pagina=b"<html>sem link</html>")) == 0
    assert [metodo for metodo, _ in pedidos] == ["GET", "HEAD"]
    assert "OpenAPI: link não encontrado na página" in capsys.readouterr().out


def test_link_fora_da_url_base_nao_e_seguido(tmp_path, capsys):
    pagina = b'{"url":"https://exemplo.invalid/swagger.json"}'
    pedidos = []
    assert rodar(tmp_path, servidor(pedidos, pagina=pagina)) == 0
    assert [metodo for metodo, _ in pedidos] == ["GET", "HEAD"]
    assert "OpenAPI: link fora da URL base, não seguido" in capsys.readouterr().out


def test_erro_de_conexao_sai_com_codigo_3(tmp_path, capsys):
    falha = httpx.ConnectError("handshake recusado (simulado)")
    assert rodar(tmp_path, servidor([], falha=falha)) == 3
    saida = capsys.readouterr()
    assert "[X] erro de conexão: ConnectError: handshake recusado (simulado)" in saida.err
    assert SENHA not in saida.out + saida.err


def test_url_de_producao_e_recusada_antes_de_qualquer_chamada(tmp_path, capsys):
    pedidos = []
    cfg = config("https://sefin.nfse.gov.br/SefinNacional")
    assert rodar(tmp_path, servidor(pedidos), cfg=cfg) == 1
    assert pedidos == []
    assert "INV-02" in capsys.readouterr().err


def test_emitente_inexistente(tmp_path, capsys):
    pedidos = []
    assert rodar(tmp_path, servidor(pedidos), nome="nao-existe") == 1
    assert pedidos == []
    assert "emitente 'nao-existe' não encontrado" in capsys.readouterr().err


def test_emitente_e_obrigatorio(capsys):
    with pytest.raises(SystemExit) as saida:
        testar_conexao.main([])
    assert saida.value.code == 2
    assert "--emitente" in capsys.readouterr().err
