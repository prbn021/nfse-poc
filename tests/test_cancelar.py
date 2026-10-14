"""Script manual de cancelamento de NFS-e em produção restrita (T-030).

Sem rede: a SEFIN é simulada com `httpx.MockTransport`, e o certificado é o autoassinado de
tests/pfx.py (DEC-014).
"""

import json
import logging
import sys

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from lxml import etree

from src.assinatura import conferir_assinatura
from src.codec import codificar, decodificar
from src.config import RAIZ, XSD_DIR_PADRAO, Config
from src.dps import NS
from tests.evento_ficticio import gerar_evento
from tests.nfse_ficticia import CHAVE
from tests.pfx import CNPJ, chave_de_teste, gerar_certificado, gerar_pfx

sys.path.insert(0, str(RAIZ / "scripts"))

import cancelar

SENHA = "s3nh4-f1ct1c14-cnc"
BASE = "https://sefin.producaorestrita.nfse.gov.br/SefinNacional"
ID_PEDIDO = f"PRE{CHAVE}101101"
MOTIVO = "Erro na emissão da nota de teste"
# Chave fictícia de outro emitente: muda o CNPJ (posições 10 a 23).
CHAVE_DE_OUTRO = CHAVE[:9] + "99888777000161" + CHAVE[23:]
EVENTOS = f"/SefinNacional/nfse/{CHAVE}/eventos"
CONSULTA = f"{EVENTOS}/101101/1"


def config(ambiente="homologacao") -> Config:
    return Config(
        ambiente=ambiente,
        sefin_url=BASE,
        adn_url="https://adn.producaorestrita.nfse.gov.br",
        xsd_dir=XSD_DIR_PADRAO,
    )


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


@pytest.fixture(scope="module")
def evento():
    return gerar_evento()


def erro(status: int, codigo: str) -> httpx.Response:
    return httpx.Response(status, json={"erro": {"codigo": codigo, "descricao": "fictício"}})


class Servidor:
    """SEFIN simulada: a consulta do evento 101101 e o `POST` do pedido."""

    def __init__(self, *, consultas=(), envio=None):
        # Cada consulta devolve o próximo item: bytes (200 com o evento), httpx.Response ou
        # Exception; sem itens, 404.
        self.consultas = list(consultas)
        self.envio = envio  # bytes: 201 com o evento; httpx.Response ou Exception
        self.pedidos = []
        self.enviado = None

    @staticmethod
    def _resolver(valor, status):
        if isinstance(valor, Exception):
            raise valor
        if isinstance(valor, bytes):
            return httpx.Response(status, json={"eventoXmlGZipB64": codificar(valor)})
        return valor

    def __call__(self, pedido: httpx.Request) -> httpx.Response:
        self.pedidos.append((pedido.method, pedido.url.path))
        if pedido.method == "GET" and pedido.url.path == CONSULTA:
            if not self.consultas:
                return erro(404, "E404")
            return self._resolver(self.consultas.pop(0), 200)
        if pedido.method == "POST" and pedido.url.path == EVENTOS:
            self.enviado = decodificar(json.loads(pedido.content)["pedidoRegistroEventoXmlGZipB64"])
            return self._resolver(self.envio, 201)
        return httpx.Response(404)


def rodar(emitentes, tmp_path, servidor, *args, chave=CHAVE, ambiente="homologacao"):
    return cancelar.main(
        [
            "--emitente",
            "acme",
            "--chave",
            chave,
            "--motivo",
            "1",
            "--descricao",
            MOTIVO,
            *args,
        ],
        pasta=emitentes,
        config=config(ambiente),
        transporte=httpx.MockTransport(servidor),
        saida=tmp_path / "out",
    )


def _arquivos(tmp_path):
    pasta = tmp_path / "out"
    return sorted(p.name for p in pasta.iterdir()) if pasta.exists() else []


# --- sem --confirmar: nada é enviado -----------------------------------------------------


def test_sem_confirmar_assina_salva_e_nao_acessa_a_rede(emitentes, tmp_path, capsys):
    servidor = Servidor()
    assert rodar(emitentes, tmp_path, servidor) == 0
    assert servidor.pedidos == []
    arquivo = tmp_path / "out" / f"{ID_PEDIDO}-assinado.xml"
    assert _arquivos(tmp_path) == [arquivo.name]
    xml = arquivo.read_bytes()
    conferir_assinatura(xml, gerar_certificado())
    inf = etree.fromstring(xml).find(f"{{{NS}}}infPedReg")
    assert inf.get("Id") == ID_PEDIDO
    assert inf.findtext(f"{{{NS}}}tpAmb") == "2"
    assert inf.findtext(f"{{{NS}}}CNPJAutor") == CNPJ
    assert inf.findtext(f"{{{NS}}}dhEvento").endswith("-03:00")
    grupo = inf.find(f"{{{NS}}}e101101")
    assert grupo.findtext(f"{{{NS}}}cMotivo") == "1"
    assert grupo.findtext(f"{{{NS}}}xMotivo") == MOTIVO
    out, err = capsys.readouterr()
    assert err == ""
    assert "Nada foi enviado" in out
    assert "--confirmar" in out


@pytest.mark.parametrize(
    ("args", "texto"),
    [
        (["--descricao", "curta demais"], "x_motivo"),
        (["--descricao", "Erro na emissão \u2013 nota de teste"], "x_motivo"),
    ],
)
def test_pedido_invalido_nao_acessa_a_rede(emitentes, tmp_path, capsys, args, texto):
    servidor = Servidor()
    assert rodar(emitentes, tmp_path, servidor, *args, "--confirmar") == 1
    assert servidor.pedidos == []
    assert texto in capsys.readouterr().err


@pytest.mark.parametrize("motivo", ["0", "3", "x"])
def test_motivo_fora_de_1_2_9(emitentes, tmp_path, motivo):
    with pytest.raises(SystemExit) as saida:
        cancelar.main(
            ["--emitente", "acme", "--chave", CHAVE, "--motivo", motivo, "--descricao", MOTIVO],
            pasta=emitentes,
            config=config(),
            saida=tmp_path / "out",
        )
    assert saida.value.code == 2


def test_chave_de_outro_emitente_nao_faz_nada(emitentes, tmp_path, capsys):
    servidor = Servidor()
    codigo = rodar(emitentes, tmp_path, servidor, "--confirmar", chave=CHAVE_DE_OUTRO)
    assert codigo == 1
    assert servidor.pedidos == []
    assert _arquivos(tmp_path) == []
    assert "não é de uma nota deste emitente" in capsys.readouterr().err


@pytest.mark.parametrize("chave", ["123", "a" * 50])
def test_chave_fora_do_formato(emitentes, tmp_path, capsys, chave):
    servidor = Servidor()
    assert rodar(emitentes, tmp_path, servidor, "--confirmar", chave=chave) == 1
    assert servidor.pedidos == []
    assert "50 dígitos" in capsys.readouterr().err


@pytest.mark.parametrize("args", [[], ["--confirmar"]])
def test_producao_e_recusada(emitentes, tmp_path, capsys, args):
    servidor = Servidor()
    assert rodar(emitentes, tmp_path, servidor, *args, ambiente="producao") == 1
    assert servidor.pedidos == []
    assert "INV-02" in capsys.readouterr().err


# --- com --confirmar --------------------------------------------------------------------


def test_cancela_confere_e_salva(emitentes, tmp_path, capsys, evento):
    servidor = Servidor(envio=evento)
    assert rodar(emitentes, tmp_path, servidor, "--confirmar") == 0
    assert servidor.pedidos == [("GET", CONSULTA), ("POST", EVENTOS)]
    assinado = (tmp_path / "out" / f"{ID_PEDIDO}-assinado.xml").read_bytes()
    assert servidor.enviado == assinado
    assert (tmp_path / "out" / f"Evento{CHAVE}-101101-1.xml").read_bytes() == evento
    out, err = capsys.readouterr()
    assert err == ""
    assert f"Chave de acesso: {CHAVE}" in out
    assert "Sequência: 1" in out
    assert "Processado em: 2026-10-12T11:00:00-03:00" in out
    assert "[OK] Evento de cancelamento conferido" in out


def test_nota_ja_cancelada_nao_envia(emitentes, tmp_path, capsys, evento):
    servidor = Servidor(consultas=[evento])
    assert rodar(emitentes, tmp_path, servidor, "--confirmar") == cancelar.JA_CANCELADA
    assert servidor.pedidos == [("GET", CONSULTA)]
    assert (tmp_path / "out" / f"Evento{CHAVE}-101101-1.xml").read_bytes() == evento
    assert "já tem evento de cancelamento" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("codigo", "dica"),
    [
        ("E0840", "consultar_nfse.py"),
        ("E0822", "prazo"),
        ("E1831", "não existe no ADN"),
        ("E1843", "relógio"),
    ],
)
def test_rejeicao_mostra_codigo_dica_e_salva_a_resposta(emitentes, tmp_path, capsys, codigo, dica):
    servidor = Servidor(envio=erro(400, codigo))
    assert rodar(emitentes, tmp_path, servidor, "--confirmar") == cancelar.REJEITADA
    assert [m for m, _ in servidor.pedidos].count("POST") == 1
    err = capsys.readouterr().err
    assert codigo in err
    assert dica in err
    respostas = [n for n in _arquivos(tmp_path) if n.startswith(f"{ID_PEDIDO}-resposta-400-")]
    assert len(respostas) == 1


def test_queda_com_evento_registrado_recupera(emitentes, tmp_path, capsys, evento):
    servidor = Servidor(consultas=[erro(404, "E404"), evento], envio=httpx.ReadTimeout("simulado"))
    assert rodar(emitentes, tmp_path, servidor, "--confirmar") == 0
    assert servidor.pedidos == [("GET", CONSULTA), ("POST", EVENTOS), ("GET", CONSULTA)]
    assert (tmp_path / "out" / f"Evento{CHAVE}-101101-1.xml").read_bytes() == evento
    out = capsys.readouterr().out
    assert "recuperado pela consulta" in out
    assert "ReadTimeout" in out


def test_queda_sem_evento_registrado(emitentes, tmp_path, capsys):
    servidor = Servidor(envio=httpx.ReadTimeout("simulado"))
    assert rodar(emitentes, tmp_path, servidor, "--confirmar") == cancelar.ERRO_DE_REDE
    assert [m for m, _ in servidor.pedidos].count("POST") == 1
    assert "pode ser enviado de novo" in capsys.readouterr().err


def test_queda_no_envio_e_na_consulta(emitentes, tmp_path, capsys):
    servidor = Servidor(
        consultas=[erro(404, "E404"), httpx.ConnectError("simulado")],
        envio=httpx.ReadTimeout("simulado"),
    )
    codigo = rodar(emitentes, tmp_path, servidor, "--confirmar")
    assert codigo == cancelar.CANCELAMENTO_INCERTO
    assert [m for m, _ in servidor.pedidos].count("POST") == 1
    assert "Não reenvie" in capsys.readouterr().err


def test_resposta_inesperada_salva_a_resposta(emitentes, tmp_path, capsys):
    servidor = Servidor(envio=httpx.Response(201, content=b"<html/>"))
    assert rodar(emitentes, tmp_path, servidor, "--confirmar") == cancelar.RESPOSTA_INESPERADA
    assert any(n.startswith(f"{ID_PEDIDO}-resposta-201-") for n in _arquivos(tmp_path))
    assert "corpo não é JSON" in capsys.readouterr().err


def test_evento_com_problema_na_conferencia(emitentes, tmp_path, capsys):
    servidor = Servidor(envio=gerar_evento(tp_amb="1"))
    assert rodar(emitentes, tmp_path, servidor, "--confirmar") == cancelar.CONFERENCIA_FALHOU
    assert (tmp_path / "out" / f"Evento{CHAVE}-101101-1.xml").exists()
    assert "tpAmb do evento não é 2" in capsys.readouterr().err


# --- INV-05 -----------------------------------------------------------------------------


def test_nada_de_senha_ou_chave_em_log_ou_saida(emitentes, tmp_path, capsys, caplog, evento):
    caplog.set_level(logging.DEBUG)
    rodar(emitentes, tmp_path, Servidor(), "--confirmar", "--descricao", "curta")
    rodar(emitentes, tmp_path, Servidor(envio=erro(400, "E0840")), "--confirmar")
    rodar(emitentes, tmp_path, Servidor(envio=evento), "--confirmar")
    saida = capsys.readouterr()
    pem = chave_de_teste().private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    miolo = pem.decode().splitlines()[1]
    for texto in (caplog.text, saida.out, saida.err):
        assert SENHA not in texto
        assert "PRIVATE KEY" not in texto
        assert miolo not in texto
