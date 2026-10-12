"""Client mTLS mínimo (T-015, DEC-031). Nenhum teste toca a rede: as chamadas HTTP passam por
`httpx.MockTransport` e o handshake TLS é feito em memória, com o PFX autoassinado de tests/pfx.py.
"""

import json
import logging
import ssl
import tempfile
from pathlib import Path

import httpx
import pytest
from cryptography.hazmat.primitives import serialization

from src.certificado import carregar_certificado
from src.client import ClienteNfse, ErroConexao, contexto_tls
from src.codec import codificar, decodificar
from src.config import Config
from src.dps import gerar_id
from src.erros import MensagemApi, RejeicaoApi, RespostaInesperada
from tests.pfx import CNPJ, gerar_pfx

SENHA = "s3nh4-f1ct1c14-xyz"
BASE = "https://sefin.producaorestrita.nfse.gov.br/SefinNacional"
ID_DPS = gerar_id("3304557", CNPJ, 49999, 1)  # fictício


@pytest.fixture(scope="module")
def cert(tmp_path_factory):
    caminho = tmp_path_factory.mktemp("pfx") / "acme.pfx"
    caminho.write_bytes(gerar_pfx(SENHA))
    return carregar_certificado(caminho, SENHA)


def config(*, ambiente="homologacao", sefin_url=BASE) -> Config:
    return Config(
        ambiente=ambiente,
        sefin_url=sefin_url,
        adn_url="https://adn.producaorestrita.nfse.gov.br",
        xsd_dir=Path("schemas/1.01"),
    )


def transporte(resposta: httpx.Response | Exception, pedidos: list | None = None):
    def responder(pedido: httpx.Request) -> httpx.Response:
        if pedidos is not None:
            pedidos.append(pedido)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta

    return httpx.MockTransport(responder)


def pem_da_chave(cert) -> bytes:
    return cert.chave.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


# --- contexto TLS ----------------------------------------------------------------------


def handshake(contexto_cliente: ssl.SSLContext, contexto_servidor: ssl.SSLContext) -> bytes:
    """Faz o handshake TLS em memória e devolve o certificado que o servidor recebeu."""
    entrada_c, saida_c, entrada_s, saida_s = (ssl.MemoryBIO() for _ in range(4))
    lado_c = contexto_cliente.wrap_bio(entrada_c, saida_c, server_hostname="localhost")
    lado_s = contexto_servidor.wrap_bio(entrada_s, saida_s, server_side=True)
    prontos = set()
    for _ in range(20):
        for nome, lado in (("c", lado_c), ("s", lado_s)):
            if nome in prontos:
                continue
            try:
                lado.do_handshake()
                prontos.add(nome)
            except ssl.SSLWantReadError:
                pass
        entrada_s.write(saida_c.read())
        entrada_c.write(saida_s.read())
        if prontos == {"c", "s"}:
            return lado_s.getpeercert(binary_form=True)
    raise AssertionError("o handshake não terminou")


def test_o_contexto_apresenta_o_certificado_do_emitente(cert, tmp_path):
    pem_cert = cert.certificado.public_bytes(serialization.Encoding.PEM)
    (tmp_path / "servidor.pem").write_bytes(pem_da_chave(cert) + pem_cert)
    servidor = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    servidor.load_cert_chain(tmp_path / "servidor.pem")
    servidor.verify_mode = ssl.CERT_REQUIRED
    servidor.load_verify_locations(cadata=pem_cert.decode("ascii"))

    contexto = contexto_tls(cert)
    assert isinstance(contexto, ssl.SSLContext)
    assert contexto.verify_mode == ssl.CERT_REQUIRED
    assert contexto.check_hostname is True
    # Só para o teste: o "servidor" usa o mesmo certificado autoassinado.
    contexto.check_hostname = False
    contexto.load_verify_locations(cadata=pem_cert.decode("ascii"))

    recebido = handshake(contexto, servidor)
    assert recebido == cert.certificado.public_bytes(serialization.Encoding.DER)


def espiar_carga(monkeypatch, *, falhar=False):
    """Troca `load_cert_chain` por uma versão que guarda o arquivo e a senha recebidos."""
    vistos = {}
    original = ssl.SSLContext.load_cert_chain

    def carregar(self, certfile, keyfile=None, password=None):
        vistos["caminho"] = Path(certfile)
        vistos["conteudo"] = Path(certfile).read_bytes()
        vistos["senha"] = password
        if falhar:
            raise ssl.SSLError("falha simulada")
        return original(self, certfile, keyfile, password)

    monkeypatch.setattr(ssl.SSLContext, "load_cert_chain", carregar)
    return vistos


def test_o_arquivo_temporario_tem_a_chave_cifrada_e_e_apagado(cert, monkeypatch):
    vistos = espiar_carga(monkeypatch)
    contexto_tls(cert)
    assert b"-----BEGIN ENCRYPTED PRIVATE KEY-----" in vistos["conteudo"]
    assert b"-----BEGIN PRIVATE KEY-----" not in vistos["conteudo"]
    assert b"-----BEGIN RSA PRIVATE KEY-----" not in vistos["conteudo"]
    assert pem_da_chave(cert) not in vistos["conteudo"]
    assert b"-----BEGIN CERTIFICATE-----" in vistos["conteudo"]
    assert not vistos["caminho"].exists()
    assert Path(tempfile.gettempdir()) == vistos["caminho"].parent


def test_a_senha_do_arquivo_temporario_e_aleatoria(cert, monkeypatch):
    vistos = espiar_carga(monkeypatch)
    contexto_tls(cert)
    primeira = vistos["senha"]
    contexto_tls(cert)
    assert len(primeira) >= 32
    assert primeira != vistos["senha"]
    assert SENHA.encode() not in (primeira, vistos["senha"])


def test_o_arquivo_temporario_e_apagado_quando_a_carga_falha(cert, monkeypatch):
    vistos = espiar_carga(monkeypatch, falhar=True)
    with pytest.raises(ValueError, match="carregar o certificado no TLS") as erro:
        contexto_tls(cert)
    assert not vistos["caminho"].exists()
    # A exceção do ssl não fica encadeada (DEC-030).
    assert erro.value.__cause__ is None
    assert erro.value.__context__ is None


# --- INV-02: só produção restrita -------------------------------------------------------


@pytest.mark.parametrize("ambiente", ["producao", "outro"])
def test_recusa_ambiente_que_nao_e_homologacao(cert, ambiente):
    with pytest.raises(ValueError, match="INV-02"):
        ClienteNfse(config(ambiente=ambiente), cert, transporte=transporte(httpx.Response(200)))


@pytest.mark.parametrize(
    "url",
    [
        "",
        "https://sefin.nfse.gov.br/SefinNacional",
        "http://sefin.producaorestrita.nfse.gov.br/SefinNacional",
        "https://producaorestrita.nfse.gov.br.exemplo.invalid/API",
        "https://exemplo.invalid/?h=sefin.producaorestrita.nfse.gov.br",
        "https://exemplo.invalid#sefin.producaorestrita.nfse.gov.br",
        "https://usuario@exemplo.invalid/sefin.producaorestrita.nfse.gov.br",
    ],
)
def test_recusa_url_fora_da_producao_restrita(cert, url):
    with pytest.raises(ValueError, match="INV-02"):
        ClienteNfse(config(sefin_url=url), cert, transporte=transporte(httpx.Response(200)))


def test_cliente_do_adn_usa_a_url_do_adn(cert):
    pedidos = []
    with ClienteNfse(
        config(), cert, api="adn", transporte=transporte(httpx.Response(200), pedidos)
    ) as cliente:
        assert cliente.base_url == "https://adn.producaorestrita.nfse.gov.br"
        cliente.obter("parametrizacao/docs/index.html")
    assert (
        pedidos[0].url == "https://adn.producaorestrita.nfse.gov.br/parametrizacao/docs/index.html"
    )


@pytest.mark.parametrize(
    "adn_url",
    ["https://adn.nfse.gov.br", "http://adn.producaorestrita.nfse.gov.br", ""],
)
def test_cliente_do_adn_recusa_url_fora_da_producao_restrita(cert, adn_url):
    cfg = Config("homologacao", BASE, adn_url, Path("x"))
    with pytest.raises(ValueError, match=r"NFSE_ADN_URL .*\(INV-02"):
        ClienteNfse(cfg, cert, api="adn", transporte=transporte(httpx.Response(200)))


def test_api_desconhecida(cert):
    with pytest.raises(ValueError, match="api"):
        ClienteNfse(config(), cert, api="outra", transporte=transporte(httpx.Response(200)))


# --- parametrização municipal no ADN (T-026) ----------------------------------------------

ADN = "https://adn.producaorestrita.nfse.gov.br"


def cliente_adn(cert, resposta, pedidos=None):
    return ClienteNfse(config(), cert, api="adn", transporte=transporte(resposta, pedidos))


@pytest.mark.parametrize("status", [200, 400, 404])
def test_convenio_devolve_status_e_corpo(cert, status):
    pedidos = []
    corpo = {"mensagem": "ok", "parametrosConvenio": {"aderenteEmissorNacional": 1}}
    with cliente_adn(cert, json_resposta(status, corpo), pedidos) as cliente:
        consulta = cliente.convenio("3304557")
    assert [(p.method, str(p.url)) for p in pedidos] == [
        ("GET", f"{ADN}/parametrizacao/3304557/convenio")
    ]
    assert consulta.status == status
    assert consulta.corpo["parametrosconvenio"] == {"aderenteEmissorNacional": 1}
    assert consulta.mensagem == "ok"


def test_historico_de_aliquotas(cert):
    pedidos = []
    corpo = {"Mensagem": None, "Aliquotas": {"041201000": [{"Aliq": 5.0}]}}
    with cliente_adn(cert, json_resposta(200, corpo), pedidos) as cliente:
        consulta = cliente.historico_aliquotas("3304557", "041201000")
    assert str(pedidos[0].url) == f"{ADN}/parametrizacao/3304557/041201000/historicoaliquotas"
    assert consulta.corpo["aliquotas"] == {"041201000": [{"Aliq": 5.0}]}
    assert consulta.mensagem is None


@pytest.mark.parametrize(
    ("municipio", "codigo"),
    [
        ("330455", "041201"),
        ("33045570", "041201"),
        ("abc4557", "041201"),
        ("3304557", "04120"),
        ("3304557", "0412010"),
        ("3304557", "04/201"),
    ],
)
def test_consultas_recusam_codigos_fora_do_formato(cert, municipio, codigo):
    pedidos = []
    with cliente_adn(cert, httpx.Response(200), pedidos) as cliente, pytest.raises(ValueError):
        cliente.historico_aliquotas(municipio, codigo)
    assert pedidos == []


@pytest.mark.parametrize(
    "resposta",
    [httpx.Response(500, content=b"erro"), httpx.Response(200, content=b"<html/>")],
)
def test_consulta_de_parametros_inesperada(cert, resposta):
    with cliente_adn(cert, resposta) as cliente, pytest.raises(RespostaInesperada) as erro:
        cliente.convenio("3304557")
    assert erro.value.corpo == resposta.content


def test_consultas_de_parametros_so_no_adn(cert):
    with (
        ClienteNfse(config(), cert, transporte=transporte(httpx.Response(200))) as cliente,
        pytest.raises(ValueError, match="ADN"),
    ):
        cliente.convenio("3304557")


def test_aceita_a_url_da_producao_restrita(cert):
    with ClienteNfse(config(), cert, transporte=transporte(httpx.Response(200))) as cliente:
        assert cliente.sefin_url == BASE


# --- consultas ----------------------------------------------------------------------------


def test_consultar_dps_faz_head_e_devolve_o_status(cert):
    pedidos = []
    resposta = httpx.Response(404)
    with ClienteNfse(config(), cert, transporte=transporte(resposta, pedidos)) as cliente:
        assert cliente.consultar_dps(ID_DPS).status == 404
    assert [(p.method, str(p.url)) for p in pedidos] == [("HEAD", f"{BASE}/dps/{ID_DPS}")]


@pytest.mark.parametrize("id_dps", ["", "DPS123", "../nfse", ID_DPS + "0", "XYZ" + ID_DPS[3:]])
def test_consultar_dps_recusa_id_fora_do_formato(cert, id_dps):
    pedidos = []
    with (
        ClienteNfse(config(), cert, transporte=transporte(httpx.Response(404), pedidos)) as c,
        pytest.raises(ValueError, match="Id da DPS"),
    ):
        c.consultar_dps(id_dps)
    assert pedidos == []


def test_obter_faz_get_relativo_a_url_base(cert):
    pedidos = []
    resposta = httpx.Response(200, headers={"content-type": "text/html"}, content=b"<html/>")
    with ClienteNfse(config(), cert, transporte=transporte(resposta, pedidos)) as cliente:
        obtida = cliente.obter("docs/index")
    assert (obtida.status, obtida.tipo, obtida.corpo) == (200, "text/html", b"<html/>")
    assert [(p.method, str(p.url)) for p in pedidos] == [("GET", f"{BASE}/docs/index")]


@pytest.mark.parametrize(
    "caminho", ["", "/docs", "../outro", "docs/../../x", "https://exemplo.invalid/x", "a b"]
)
def test_obter_recusa_caminho_fora_da_url_base(cert, caminho):
    pedidos = []
    with (
        ClienteNfse(config(), cert, transporte=transporte(httpx.Response(200), pedidos)) as c,
        pytest.raises(ValueError, match="caminho"),
    ):
        c.obter(caminho)
    assert pedidos == []


def test_erro_de_conexao_vira_erro_conexao(cert):
    falha = httpx.ConnectError("conexão recusada (simulada)")
    with (
        ClienteNfse(config(), cert, transporte=transporte(falha)) as cliente,
        pytest.raises(ErroConexao, match="ConnectError: conexão recusada") as erro,
    ):
        cliente.consultar_dps(ID_DPS)
    assert erro.value.__cause__ is None
    assert erro.value.__context__ is None


# --- envio e consultas da API (T-007) ---------------------------------------------------


CHAVE = "3" * 50  # fictícia
NFSE_XML = "<NFSe>fictícia</NFSe>".encode()
QUANDO = "2026-10-12T10:00:00-03:00"


def json_resposta(status: int, corpo) -> httpx.Response:
    return httpx.Response(status, json=corpo)


def sucesso(**over) -> dict:
    corpo = {
        "tipoAmbiente": 2,
        "versaoAplicativo": "Ficticio_1.0",
        "dataHoraProcessamento": QUANDO,
        "idDps": ID_DPS,
        "chaveAcesso": CHAVE,
        "nfseXmlGZipB64": codificar(NFSE_XML),
        "alertas": [{"codigo": "A0001", "descricao": "alerta fictício", "complemento": None}],
    }
    corpo.update(over)
    return corpo


def erro_post(*erros, status=400) -> httpx.Response:
    return json_resposta(
        status,
        {
            "tipoAmbiente": 2,
            "versaoAplicativo": "Ficticio_1.0",
            "dataHoraProcessamento": QUANDO,
            "idDPS": ID_DPS,
            "erros": [{"codigo": c, "descricao": d, "complemento": None} for c, d in erros],
        },
    )


def test_emitir_faz_post_com_a_dps_em_gzip_base64(cert):
    pedidos = []
    with ClienteNfse(
        config(), cert, transporte=transporte(json_resposta(201, sucesso()), pedidos)
    ) as cliente:
        emitida = cliente.emitir(b"<DPS/>")
    [pedido] = pedidos
    assert (pedido.method, str(pedido.url)) == ("POST", f"{BASE}/nfse")
    assert pedido.headers["content-type"] == "application/json"
    assert decodificar(json.loads(pedido.content)["dpsXmlGZipB64"]) == b"<DPS/>"
    assert emitida.chave == CHAVE
    assert emitida.id_dps == ID_DPS
    assert emitida.xml == NFSE_XML
    assert emitida.alertas == (MensagemApi("A0001", "alerta fictício", None),)


def test_emitir_sem_alertas(cert):
    resposta = json_resposta(201, sucesso(alertas=None))
    with ClienteNfse(config(), cert, transporte=transporte(resposta)) as cliente:
        assert cliente.emitir(b"<DPS/>").alertas == ()


@pytest.mark.parametrize("status", [400, 403, 500])
def test_emitir_rejeitada_traz_status_id_e_mensagens(cert, status):
    resposta = erro_post(
        ("E0014", "Conjunto já existe"), ("E0008", "Data de emissão posterior"), status=status
    )
    with (
        ClienteNfse(config(), cert, transporte=transporte(resposta)) as cliente,
        pytest.raises(RejeicaoApi) as erro,
    ):
        cliente.emitir(b"<DPS/>")
    assert erro.value.status == status
    assert erro.value.id_dps == ID_DPS
    assert [m.codigo for m in erro.value.mensagens] == ["E0014", "E0008"]
    texto = str(erro.value)
    assert f"HTTP {status}" in texto
    assert "E0014: Conjunto já existe" in texto
    assert "E0008: Data de emissão posterior" in texto


@pytest.mark.parametrize(
    ("resposta", "motivo"),
    [
        (httpx.Response(201, content=b"<html/>"), "não é JSON"),
        (json_resposta(201, ["lista"]), "não é um objeto JSON"),
        (json_resposta(201, sucesso(chaveAcesso=None)), "chaveAcesso"),
        (json_resposta(201, sucesso(chaveAcesso="123")), "chaveAcesso"),
        (json_resposta(201, sucesso(idDps="DPS1")), "idDps"),
        (json_resposta(201, sucesso(nfseXmlGZipB64="não é base64")), "nfseXmlGZipB64"),
        (json_resposta(201, sucesso(alertas="x")), "alertas"),
        (json_resposta(400, {"erros": "x"}), "erros"),
        (httpx.Response(400, content=b""), "não é JSON"),
        (httpx.Response(502, content=b"Bad Gateway"), "HTTP 502"),
        (json_resposta(200, sucesso()), "HTTP 200"),
    ],
)
def test_emitir_resposta_inesperada(cert, resposta, motivo):
    with (
        ClienteNfse(config(), cert, transporte=transporte(resposta)) as cliente,
        pytest.raises(RespostaInesperada, match=motivo) as erro,
    ):
        cliente.emitir(b"<DPS/>")
    # O corpo bruto da resposta não vai para a mensagem.
    assert "Bad Gateway" not in str(erro.value)
    assert "<html/>" not in str(erro.value)


@pytest.mark.parametrize(
    ("item", "esperada"),
    [
        # Fora do formato da especificação: a primeira transmissão real veio assim (DEC-037).
        ({"Codigo": "E0014", "Descricao": "já existe"}, MensagemApi("E0014", "já existe")),
        ({"CODIGO": "E1", "DESCRICAO": "x", "COMPLEMENTO": "y"}, MensagemApi("E1", "x", "y")),
        ({"codigo": "E0008", "descricao": None}, MensagemApi("E0008", "")),
        ({"codigo": 714, "descricao": "assinatura"}, MensagemApi("714", "assinatura")),
        ({"descricao": "sem código"}, MensagemApi("?", "sem código")),
        (
            {"complemento": "só complemento"},
            MensagemApi("?", "item sem codigo nem descricao", "só complemento"),
        ),
        ({}, MensagemApi("?", "item sem codigo nem descricao")),
        ("texto solto", MensagemApi("?", "texto solto")),
        (None, MensagemApi("?", "item vazio")),
    ],
)
def test_mensagens_fora_do_formato_sao_lidas_com_tolerancia(cert, item, esperada):
    resposta = json_resposta(400, {"idDPS": ID_DPS, "erros": [item]})
    with (
        ClienteNfse(config(), cert, transporte=transporte(resposta)) as cliente,
        pytest.raises(RejeicaoApi) as erro,
    ):
        cliente.emitir(b"<DPS/>")
    assert erro.value.mensagens == (esperada,)


def test_emitir_aceita_campos_com_outra_capitalizacao(cert):
    # A resposta de erro real veio em PascalCase (DEC-037); a de sucesso pode vir também.
    corpo = {
        "TipoAmbiente": 2,
        "IdDps": ID_DPS,
        "ChaveAcesso": CHAVE,
        "NfseXmlGZipB64": codificar(NFSE_XML),
        "Alertas": [{"Codigo": "A1", "Descricao": "alerta fictício"}],
    }
    with ClienteNfse(config(), cert, transporte=transporte(json_resposta(201, corpo))) as c:
        emitida = c.emitir(b"<DPS/>")
    assert (emitida.chave, emitida.id_dps, emitida.xml) == (CHAVE, ID_DPS, NFSE_XML)
    assert emitida.alertas == (MensagemApi("A1", "alerta fictício"),)


def test_consultas_aceitam_campos_com_outra_capitalizacao(cert):
    resposta = json_resposta(200, {"ChaveAcesso": CHAVE, "IdDps": ID_DPS})
    with ClienteNfse(config(), cert, transporte=transporte(resposta)) as cliente:
        assert cliente.chave_da_dps(ID_DPS) == CHAVE
    resposta = json_resposta(200, {"ChaveAcesso": CHAVE, "NFSEXMLGZIPB64": codificar(NFSE_XML)})
    with ClienteNfse(config(), cert, transporte=transporte(resposta)) as cliente:
        assert cliente.obter_nfse(CHAVE) == NFSE_XML


@pytest.mark.parametrize(
    "corpo",
    [
        {"IdDPS": ID_DPS, "Erros": [{"Codigo": "E1", "Descricao": "x"}]},
        {"idDps": ID_DPS, "ERROS": [{"Codigo": "E1", "Descricao": "x"}]},
        {"IdDPS": ID_DPS, "Erro": {"Codigo": "E1", "Descricao": "x"}},
    ],
)
def test_rejeicao_com_campos_em_outra_capitalizacao(cert, corpo):
    with (
        ClienteNfse(config(), cert, transporte=transporte(json_resposta(400, corpo))) as c,
        pytest.raises(RejeicaoApi) as erro,
    ):
        c.emitir(b"<DPS/>")
    assert erro.value.id_dps == ID_DPS
    assert erro.value.mensagens == (MensagemApi("E1", "x"),)


def test_rejeicao_guarda_o_corpo_bruto_fora_da_mensagem(cert):
    resposta = json_resposta(400, {"erros": [{"codigo": "E1", "descricao": "x"}], "extra": "Z9"})
    with (
        ClienteNfse(config(), cert, transporte=transporte(resposta)) as cliente,
        pytest.raises(RejeicaoApi) as erro,
    ):
        cliente.emitir(b"<DPS/>")
    assert erro.value.corpo == resposta.content
    assert "Z9" not in str(erro.value)


@pytest.mark.parametrize(
    "resposta",
    [httpx.Response(502, content=b"Bad Gateway"), json_resposta(201, sucesso(chaveAcesso="1"))],
)
def test_resposta_inesperada_guarda_o_corpo_bruto(cert, resposta):
    with (
        ClienteNfse(config(), cert, transporte=transporte(resposta)) as cliente,
        pytest.raises(RespostaInesperada) as erro,
    ):
        cliente.emitir(b"<DPS/>")
    assert erro.value.corpo == resposta.content


def test_rejeicao_na_consulta_guarda_o_corpo(cert):
    resposta = json_resposta(400, {"erro": {"codigo": "E400", "descricao": "Id inválido"}})
    with (
        ClienteNfse(config(), cert, transporte=transporte(resposta)) as cliente,
        pytest.raises(RejeicaoApi) as erro,
    ):
        cliente.chave_da_dps(ID_DPS)
    assert erro.value.corpo == resposta.content


def test_emitir_erro_de_conexao(cert):
    with (
        ClienteNfse(config(), cert, transporte=transporte(httpx.ReadTimeout("simulado"))) as c,
        pytest.raises(ErroConexao, match="ReadTimeout"),
    ):
        c.emitir(b"<DPS/>")


def test_emitir_so_aceita_bytes(cert):
    pedidos = []
    with (
        ClienteNfse(config(), cert, transporte=transporte(httpx.Response(201), pedidos)) as c,
        pytest.raises(TypeError, match="bytes"),
    ):
        c.emitir("<DPS/>")
    assert pedidos == []


def test_chave_da_dps_existente(cert):
    pedidos = []
    resposta = json_resposta(
        200,
        {
            "tipoAmbiente": 2,
            "versaoAplicativo": "x",
            "dataHoraProcessamento": QUANDO,
            "idDps": ID_DPS,
            "chaveAcesso": CHAVE,
        },
    )
    with ClienteNfse(config(), cert, transporte=transporte(resposta, pedidos)) as cliente:
        assert cliente.chave_da_dps(ID_DPS) == CHAVE
    assert [(p.method, str(p.url)) for p in pedidos] == [("GET", f"{BASE}/dps/{ID_DPS}")]


def test_chave_da_dps_inexistente(cert):
    resposta = json_resposta(
        404, {"erro": {"codigo": "E404", "descricao": "não encontrada", "complemento": None}}
    )
    with ClienteNfse(config(), cert, transporte=transporte(resposta)) as cliente:
        assert cliente.chave_da_dps(ID_DPS) is None


def test_chave_da_dps_com_erro_400(cert):
    resposta = json_resposta(
        400, {"erro": {"codigo": "E400", "descricao": "Id inválido", "complemento": None}}
    )
    with (
        ClienteNfse(config(), cert, transporte=transporte(resposta)) as cliente,
        pytest.raises(RejeicaoApi, match="E400: Id inválido"),
    ):
        cliente.chave_da_dps(ID_DPS)


def test_chave_da_dps_recusa_id_fora_do_formato(cert):
    pedidos = []
    with (
        ClienteNfse(config(), cert, transporte=transporte(httpx.Response(200), pedidos)) as c,
        pytest.raises(ValueError, match="Id da DPS"),
    ):
        c.chave_da_dps("DPS123")
    assert pedidos == []


def test_obter_nfse_pela_chave(cert):
    pedidos = []
    resposta = json_resposta(
        200,
        {
            "tipoAmbiente": 2,
            "versaoAplicativo": "x",
            "dataHoraProcessamento": QUANDO,
            "chaveAcesso": CHAVE,
            "nfseXmlGZipB64": codificar(NFSE_XML),
        },
    )
    with ClienteNfse(config(), cert, transporte=transporte(resposta, pedidos)) as cliente:
        assert cliente.obter_nfse(CHAVE) == NFSE_XML
    assert [(p.method, str(p.url)) for p in pedidos] == [("GET", f"{BASE}/nfse/{CHAVE}")]


@pytest.mark.parametrize("chave", ["", "123", "a" * 50, CHAVE + "0", "../" + CHAVE[3:]])
def test_obter_nfse_recusa_chave_fora_do_formato(cert, chave):
    pedidos = []
    with (
        ClienteNfse(config(), cert, transporte=transporte(httpx.Response(200), pedidos)) as c,
        pytest.raises(ValueError, match="chave de acesso"),
    ):
        c.obter_nfse(chave)
    assert pedidos == []


# --- INV-05 -----------------------------------------------------------------------------


def test_repr_do_cliente_mostra_so_a_url(cert):
    with ClienteNfse(config(), cert, transporte=transporte(httpx.Response(200))) as cliente:
        texto = repr(cliente)
    assert texto == f"ClienteNfse(sefin_url={BASE!r})"


def test_nada_de_senha_ou_chave_em_log_saida_ou_erro(cert, caplog, capsys, monkeypatch):
    caplog.set_level(logging.DEBUG)
    with ClienteNfse(config(), cert, transporte=transporte(httpx.Response(404))) as cliente:
        cliente.consultar_dps(ID_DPS)
    falha = httpx.ConnectError("falha simulada")
    with (
        ClienteNfse(config(), cert, transporte=transporte(falha)) as cliente,
        pytest.raises(ErroConexao) as erro_conexao,
    ):
        cliente.obter("docs/index")
    espiar_carga(monkeypatch, falhar=True)
    with pytest.raises(ValueError) as erro_tls:
        contexto_tls(cert)

    saida = capsys.readouterr()
    textos = [caplog.text, saida.out, saida.err, str(erro_conexao.value), str(erro_tls.value)]
    for texto in textos:
        assert SENHA not in texto
        assert "PRIVATE KEY" not in texto
