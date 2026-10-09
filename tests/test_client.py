"""Client mTLS mínimo (T-015, DEC-031). Nenhum teste toca a rede: as chamadas HTTP passam por
`httpx.MockTransport` e o handshake TLS é feito em memória, com o PFX autoassinado de tests/pfx.py.
"""

import logging
import ssl
import tempfile
from pathlib import Path

import httpx
import pytest
from cryptography.hazmat.primitives import serialization

from src.certificado import carregar_certificado
from src.client import ClienteNfse, ErroConexao, contexto_tls
from src.config import Config
from src.dps import gerar_id
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
