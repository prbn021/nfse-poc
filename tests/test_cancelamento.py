"""Fluxo do cancelamento (T-030): consulta antes, nunca reenvia, recupera o evento depois de uma
queda.

O cliente aqui é um dublê que registra as chamadas; o HTTP de verdade é testado em
tests/test_client.py.
"""

from functools import partial
from pathlib import Path

import pytest

from src import cancelamento
from src.assinatura import assinar_pedido_evento, conferir_assinatura_do_sistema
from src.cancelamento import CancelamentoIncerto, NotaJaCancelada
from src.certificado import Certificado
from src.config import XSD_DIR_PADRAO
from src.dominio.erros import ErroConexao, MensagemApi, RejeicaoApi, RespostaInesperada
from src.dominio.evento import localizar_xsd_evento
from tests.evento_ficticio import gerar_evento
from tests.nfse_ficticia import CHAVE
from tests.pfx import chave_de_teste, gerar_certificado

# Com o adaptador de assinatura de verdade, como os scripts o montam (T-043).
cancelar = partial(cancelamento.cancelar, conferir_assinatura=conferir_assinatura_do_sistema)

PEDIDO = (Path(__file__).parent / "dados" / "pedido-cancelamento.xml").read_bytes()
ID_PEDIDO = f"PRE{CHAVE}101101"


@pytest.fixture(scope="module")
def xsd():
    return localizar_xsd_evento(XSD_DIR_PADRAO)


@pytest.fixture(scope="module")
def assinado():
    cert = Certificado(certificado=gerar_certificado(), chave=chave_de_teste(), cadeia=())
    return assinar_pedido_evento(PEDIDO, cert)


@pytest.fixture(scope="module")
def evento():
    return gerar_evento()


class Dubl:
    """Cliente falso: cada método devolve ou levanta o que foi configurado, na ordem."""

    def __init__(self, *, consultas=(None,), envio=None):
        self.consultas = list(consultas)
        self.envio = envio
        self.chamadas = []

    @staticmethod
    def _resolver(valor):
        if isinstance(valor, Exception):
            raise valor
        return valor

    def consultar_evento(self, chave, tipo, seq):
        self.chamadas.append(("consultar_evento", (chave, tipo, seq)))
        return self._resolver(self.consultas.pop(0))

    def registrar_evento(self, chave, pedido):
        self.chamadas.append(("registrar_evento", (chave, pedido)))
        return self._resolver(self.envio)


def _nomes(dubl):
    return [nome for nome, _ in dubl.chamadas]


def test_consulta_antes_e_envia_uma_vez(assinado, evento, xsd):
    dubl = Dubl(envio=evento)
    resultado = cancelar(dubl, assinado, xsd)
    assert dubl.chamadas == [
        ("consultar_evento", (CHAVE, "101101", 1)),
        ("registrar_evento", (CHAVE, assinado)),
    ]
    assert resultado.evento == evento
    assert resultado.problemas == []
    assert resultado.recuperado is False
    assert resultado.falha is None


def test_nota_ja_cancelada_nao_envia(assinado, evento, xsd):
    dubl = Dubl(consultas=[evento])
    with pytest.raises(NotaJaCancelada, match="já tem evento de cancelamento") as erro:
        cancelar(dubl, assinado, xsd)
    assert _nomes(dubl) == ["consultar_evento"]
    assert erro.value.chave == CHAVE
    assert erro.value.evento == evento


def test_rejeicao_passa_adiante_sem_reenviar(assinado, xsd):
    rejeicao = RejeicaoApi(400, None, (MensagemApi("E0840", "outro evento vinculado"),))
    dubl = Dubl(envio=rejeicao)
    with pytest.raises(RejeicaoApi) as erro:
        cancelar(dubl, assinado, xsd)
    assert erro.value is rejeicao
    assert _nomes(dubl) == ["consultar_evento", "registrar_evento"]


@pytest.mark.parametrize(
    "falha",
    [ErroConexao("ReadTimeout: simulado"), RespostaInesperada(500, "HTTP 500 não previsto")],
)
def test_falha_no_envio_com_evento_registrado_recupera(assinado, evento, xsd, falha):
    dubl = Dubl(consultas=[None, evento], envio=falha)
    resultado = cancelar(dubl, assinado, xsd)
    assert _nomes(dubl) == ["consultar_evento", "registrar_evento", "consultar_evento"]
    assert resultado.evento == evento
    assert resultado.recuperado is True
    assert resultado.falha is falha
    assert resultado.problemas == []


def test_queda_sem_evento_registrado_diz_que_pode_reenviar(assinado, xsd):
    dubl = Dubl(consultas=[None, None], envio=ErroConexao("ReadTimeout: simulado"))
    with pytest.raises(ErroConexao, match="nenhum evento foi registrado") as erro:
        cancelar(dubl, assinado, xsd)
    assert "ReadTimeout: simulado" in str(erro.value)
    assert _nomes(dubl).count("registrar_evento") == 1


def test_resposta_inesperada_sem_evento_registrado_passa_adiante(assinado, xsd):
    falha = RespostaInesperada(500, "HTTP 500 não previsto")
    dubl = Dubl(consultas=[None, None], envio=falha)
    with pytest.raises(RespostaInesperada) as erro:
        cancelar(dubl, assinado, xsd)
    assert erro.value is falha


def test_queda_no_envio_e_na_consulta_e_incerto(assinado, xsd):
    dubl = Dubl(
        consultas=[None, ErroConexao("de novo")], envio=ErroConexao("ReadTimeout: simulado")
    )
    with pytest.raises(CancelamentoIncerto, match="Não reenvie") as erro:
        cancelar(dubl, assinado, xsd)
    assert erro.value.chave == CHAVE
    assert _nomes(dubl).count("registrar_evento") == 1


def test_evento_devolvido_e_conferido(assinado, xsd):
    dubl = Dubl(envio=gerar_evento(tp_amb="1"))
    resultado = cancelar(dubl, assinado, xsd)
    assert resultado.problemas == ["tpAmb do evento não é 2 (produção restrita)"]


def test_evento_devolvido_de_outro_pedido(assinado, xsd):
    dubl = Dubl(envio=gerar_evento(id_pedido=f"PRE{'1' * 56}"))
    resultado = cancelar(dubl, assinado, xsd)
    assert resultado.problemas == ["o evento não é do pedido enviado (Id do pedido diferente)"]


@pytest.mark.parametrize(
    ("xml", "texto"),
    [
        (b"nao e xml", "pedRegEvento"),
        (b"<outra/>", "pedRegEvento"),
        (PEDIDO, "assinado"),
        (PEDIDO.replace(b'101101"', b'101103"', 1), "Id"),
    ],
)
def test_pedido_invalido_nao_consulta_nem_envia(xml, texto, xsd):
    dubl = Dubl()
    with pytest.raises(ValueError, match=texto):
        cancelar(dubl, xml, xsd)
    assert dubl.chamadas == []
