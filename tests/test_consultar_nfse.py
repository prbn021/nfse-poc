"""Script manual de consulta da NFS-e por chave e dos eventos dela (T-028, DEC-051).

Sem rede: a SEFIN é simulada com `httpx.MockTransport`, e o certificado é o autoassinado de
tests/pfx.py (DEC-014).
"""

import sys
from pathlib import Path

import httpx
import pytest

from src.assinatura import assinar_dps
from src.certificado import Certificado
from src.codec import codificar
from src.config import RAIZ, XSD_DIR_PADRAO, Config
from tests.evento_ficticio import CANCELAMENTO, gerar_evento
from tests.nfse_ficticia import CHAVE, gerar_nfse
from tests.pfx import CNPJ, chave_de_teste, gerar_certificado, gerar_pfx

sys.path.insert(0, str(RAIZ / "scripts"))

import consultar_nfse

SENHA = "s3nh4-f1ct1c14-cns"
BASE = "https://sefin.producaorestrita.nfse.gov.br/SefinNacional"
DPS = (Path(__file__).parent / "dados" / "dps-sem-opcionais.xml").read_bytes()
# Chave fictícia de outro emitente: muda o CNPJ (posições 10 a 23).
CHAVE_DE_OUTRO = CHAVE[:9] + "99888777000161" + CHAVE[23:]


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
def nfse():
    cert = Certificado(certificado=gerar_certificado(), chave=chave_de_teste(), cadeia=())
    return gerar_nfse(assinar_dps(DPS, cert))


@pytest.fixture(scope="module")
def evento():
    return gerar_evento()


def erro(status: int) -> httpx.Response:
    return httpx.Response(status, json={"erro": {"codigo": f"E{status}", "descricao": "fictício"}})


class Servidor:
    """SEFIN simulada: `GET /nfse/{chave}` e `GET /nfse/{chave}/eventos/{tipo}/{seq}`."""

    def __init__(self, nfse: bytes, *, nota=None, evento=None):
        self.nfse = nfse
        self.nota = nota  # None: 200 com a NFS-e; httpx.Response: devolve
        self.evento = evento  # bytes: 200 com o evento; httpx.Response: devolve; None: 404
        self.pedidos = []

    def __call__(self, pedido: httpx.Request) -> httpx.Response:
        self.pedidos.append((pedido.method, pedido.url.path))
        caminho = pedido.url.path.removeprefix("/SefinNacional/")
        if caminho == f"nfse/{CHAVE}":
            if self.nota is not None:
                return self.nota
            return httpx.Response(
                200, json={"chaveAcesso": CHAVE, "nfseXmlGZipB64": codificar(self.nfse)}
            )
        if caminho.startswith(f"nfse/{CHAVE}/eventos/"):
            if isinstance(self.evento, bytes):
                return httpx.Response(200, json={"eventoXmlGZipB64": codificar(self.evento)})
            if self.evento is not None:
                return self.evento
            return erro(404)
        return httpx.Response(404)


def rodar(emitentes, tmp_path, servidor, *args, chave=CHAVE, ambiente="homologacao"):
    return consultar_nfse.main(
        ["--emitente", "acme", "--chave", chave, *args],
        pasta=emitentes,
        config=config(ambiente),
        transporte=httpx.MockTransport(servidor),
        saida=tmp_path / "out",
    )


def test_consulta_a_nota_confere_e_salva(emitentes, tmp_path, capsys, nfse):
    servidor = Servidor(nfse)
    assert rodar(emitentes, tmp_path, servidor) == 0
    assert servidor.pedidos == [("GET", f"/SefinNacional/nfse/{CHAVE}")]
    assert (tmp_path / "out" / f"NFSe{CHAVE}-consulta.xml").read_bytes() == nfse
    out, err = capsys.readouterr()
    assert err == ""
    assert f"Chave de acesso: {CHAVE}" in out
    assert "Número: 1" in out
    assert "cStat: 100" in out
    assert "[OK] NFS-e conferida" in out
    # Só chave, número e situação: nada do tomador nem dos valores.
    assert "100.00" not in out
    assert SENHA not in out


def test_consulta_o_evento_quando_pedido(emitentes, tmp_path, capsys, nfse, evento):
    servidor = Servidor(nfse, evento=evento)
    assert rodar(emitentes, tmp_path, servidor, "--evento", CANCELAMENTO) == 0
    assert servidor.pedidos[-1] == ("GET", f"/SefinNacional/nfse/{CHAVE}/eventos/101101/1")
    arquivo = tmp_path / "out" / f"Evento{CHAVE}-101101-1.xml"
    assert arquivo.read_bytes() == evento
    out = capsys.readouterr().out
    assert "[OK] Evento 101101 (sequência 1) conferido" in out


def test_numero_sequencial_vem_do_argumento(emitentes, tmp_path, nfse, evento):
    servidor = Servidor(nfse, evento=evento)
    rodar(emitentes, tmp_path, servidor, "--evento", CANCELAMENTO, "--seq", "2")
    assert servidor.pedidos[-1] == ("GET", f"/SefinNacional/nfse/{CHAVE}/eventos/101101/2")


def test_sem_evento_nao_e_erro(emitentes, tmp_path, capsys, nfse):
    servidor = Servidor(nfse)
    assert rodar(emitentes, tmp_path, servidor, "--evento", CANCELAMENTO) == 0
    assert "Nenhum evento 101101 (sequência 1)" in capsys.readouterr().out
    assert not list((tmp_path / "out").glob("Evento*"))


def test_seq_sem_evento_e_recusado(emitentes, tmp_path, capsys, nfse):
    servidor = Servidor(nfse)
    with pytest.raises(SystemExit) as saida:
        rodar(emitentes, tmp_path, servidor, "--seq", "2")
    assert saida.value.code == 2
    assert servidor.pedidos == []


@pytest.mark.parametrize("status", [401, 403, 404])
def test_nota_rejeitada(emitentes, tmp_path, capsys, nfse, status):
    servidor = Servidor(nfse, nota=erro(status))
    assert rodar(emitentes, tmp_path, servidor) == consultar_nfse.REJEITADA
    assert f"E{status}" in capsys.readouterr().err
    assert list((tmp_path / "out").glob(f"NFSe{CHAVE}-resposta-{status}-*.json"))


@pytest.mark.parametrize("status", [401, 422])
def test_evento_rejeitado(emitentes, tmp_path, capsys, nfse, status):
    servidor = Servidor(nfse, evento=erro(status))
    assert (
        rodar(emitentes, tmp_path, servidor, "--evento", CANCELAMENTO) == consultar_nfse.REJEITADA
    )
    assert f"E{status}" in capsys.readouterr().err


@pytest.mark.parametrize(
    "resposta",
    [httpx.Response(200, content=b"<html/>"), httpx.Response(200, json={"nfseXmlGZipB64": "!"})],
    ids=["sem-json", "base64-invalido"],
)
def test_resposta_inesperada(emitentes, tmp_path, capsys, nfse, resposta):
    servidor = Servidor(nfse, nota=resposta)
    assert rodar(emitentes, tmp_path, servidor) == consultar_nfse.RESPOSTA_INESPERADA
    assert not (tmp_path / "out" / f"NFSe{CHAVE}-consulta.xml").exists()


def test_nota_com_problema_na_conferencia(emitentes, tmp_path, capsys, nfse):
    alterada = nfse.replace(b"<vLiq>100.00</vLiq>", b"<vLiq>999.00</vLiq>", 1)
    servidor = Servidor(alterada)
    assert rodar(emitentes, tmp_path, servidor) == consultar_nfse.CONFERENCIA_FALHOU
    # A nota é salva mesmo assim, para quem rodou decidir.
    assert (tmp_path / "out" / f"NFSe{CHAVE}-consulta.xml").exists()
    assert "assinatura da NFS-e não confere" in capsys.readouterr().err


def test_evento_com_problema_na_conferencia(emitentes, tmp_path, capsys, nfse):
    servidor = Servidor(nfse, evento=gerar_evento(tp_amb="1"))
    assert (
        rodar(emitentes, tmp_path, servidor, "--evento", CANCELAMENTO)
        == consultar_nfse.CONFERENCIA_FALHOU
    )
    assert "tpAmb do evento não é 2" in capsys.readouterr().err


def test_chave_de_outro_emitente_nao_consulta(emitentes, tmp_path, capsys, nfse):
    servidor = Servidor(nfse)
    assert rodar(emitentes, tmp_path, servidor, chave=CHAVE_DE_OUTRO) == 1
    assert servidor.pedidos == []
    assert "não é de uma nota deste emitente" in capsys.readouterr().err


@pytest.mark.parametrize("chave", ["123", "a" * 50])
def test_chave_fora_do_formato_nao_consulta(emitentes, tmp_path, capsys, nfse, chave):
    servidor = Servidor(nfse)
    assert rodar(emitentes, tmp_path, servidor, chave=chave) == 1
    assert servidor.pedidos == []
    assert "chave de acesso" in capsys.readouterr().err


def test_producao_e_recusada_antes_de_qualquer_chamada(emitentes, tmp_path, capsys, nfse):
    servidor = Servidor(nfse)
    assert rodar(emitentes, tmp_path, servidor, ambiente="producao") == 1
    assert servidor.pedidos == []


def test_erro_de_rede(emitentes, tmp_path, capsys, nfse):
    def cair(pedido):
        raise httpx.ConnectError("sem rede")

    assert (
        consultar_nfse.main(
            ["--emitente", "acme", "--chave", CHAVE],
            pasta=emitentes,
            config=config(),
            transporte=httpx.MockTransport(cair),
            saida=tmp_path / "out",
        )
        == consultar_nfse.ERRO_DE_REDE
    )


@pytest.mark.parametrize("argv", [[], ["--emitente", "acme"], ["--chave", CHAVE]])
def test_emitente_e_chave_sao_obrigatorios(argv, capsys):
    with pytest.raises(SystemExit) as saida:
        consultar_nfse.main(argv)
    assert saida.value.code == 2
