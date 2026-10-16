"""Conferência do evento devolvido pela consulta de eventos (T-028, DEC-051)."""

from functools import partial

import pytest

from src.assinatura import conferir_assinatura_do_sistema
from src.config import XSD_DIR_PADRAO
from src.dominio import evento as dominio_evento
from src.dominio.evento import localizar_xsd_evento
from tests.evento_ficticio import CANCELAMENTO, gerar_evento
from tests.nfse_ficticia import CHAVE

# A conferência com o adaptador de assinatura de verdade, como os scripts a montam (T-043).
conferir_evento = partial(
    dominio_evento.conferir_evento, conferir_assinatura=conferir_assinatura_do_sistema
)


@pytest.fixture(scope="module")
def xsd():
    return localizar_xsd_evento(XSD_DIR_PADRAO)


@pytest.fixture(scope="module")
def evento():
    return gerar_evento()


def test_localiza_o_xsd_do_evento(xsd):
    assert xsd.name == "evento_v1.01.xsd"


def test_evento_correto_nao_tem_problemas(evento, xsd):
    assert conferir_evento(evento, chave=CHAVE, tipo=CANCELAMENTO, xsd=xsd) == []


def test_evento_de_outra_nota(evento, xsd):
    problemas = conferir_evento(evento, chave="1" * 50, tipo=CANCELAMENTO, xsd=xsd)
    assert problemas == ["o evento não é da NFS-e consultada (chNFSe diferente)"]


def test_evento_de_outro_tipo(evento, xsd):
    problemas = conferir_evento(evento, chave=CHAVE, tipo="105102", xsd=xsd)
    assert problemas == ["o evento não é do tipo pedido (105102)"]


def test_ambiente_de_producao_e_apontado(xsd):
    problemas = conferir_evento(gerar_evento(tp_amb="1"), chave=CHAVE, tipo=CANCELAMENTO, xsd=xsd)
    assert problemas == ["tpAmb do evento não é 2 (produção restrita)"]


def test_evento_sem_assinatura(xsd):
    problemas = conferir_evento(
        gerar_evento(assinar=False), chave=CHAVE, tipo=CANCELAMENTO, xsd=xsd
    )
    assert "assinatura do evento não confere com o certificado que ele traz" in problemas
    # O XSD exige a assinatura do sistema no evento.
    assert any(p.startswith("inválido contra evento_v1.01.xsd") for p in problemas)


def test_evento_alterado_depois_de_assinado(evento, xsd):
    alterado = evento.replace(b"<cMotivo>1</cMotivo>", b"<cMotivo>2</cMotivo>", 1)
    problemas = conferir_evento(alterado, chave=CHAVE, tipo=CANCELAMENTO, xsd=xsd)
    assert problemas == ["assinatura do evento não confere com o certificado que ele traz"]


def test_evento_fora_do_xsd(xsd):
    # cMotivo 7 não existe para o cancelamento (Anexo II: 1, 2 ou 9).
    xml = gerar_evento().replace(b"<cMotivo>1</cMotivo>", b"<cMotivo>7</cMotivo>", 1)
    problemas = conferir_evento(xml, chave=CHAVE, tipo=CANCELAMENTO, xsd=xsd)
    assert any(p.startswith("inválido contra evento_v1.01.xsd") for p in problemas)


@pytest.mark.parametrize("xml", [b"", b"nao e xml", b"<outra/>"])
def test_conteudo_que_nao_e_evento(xml, xsd):
    problemas = conferir_evento(xml, chave=CHAVE, tipo=CANCELAMENTO, xsd=xsd)
    assert problemas == ["o retorno não é um evento em XML"]


# --- Id do pedido dentro do evento (T-030) ----------------------------------------------

ID_PEDIDO = f"PRE{CHAVE}{CANCELAMENTO}"


def test_evento_do_pedido_enviado_nao_tem_problemas(evento, xsd):
    problemas = conferir_evento(
        evento, chave=CHAVE, tipo=CANCELAMENTO, xsd=xsd, id_pedido=ID_PEDIDO
    )
    assert problemas == []


def test_evento_de_outro_pedido(xsd):
    # Outro Id, válido no XSD, com a mesma chave e o mesmo tipo.
    outro = gerar_evento(id_pedido=f"PRE{'1' * 56}")
    problemas = conferir_evento(outro, chave=CHAVE, tipo=CANCELAMENTO, xsd=xsd, id_pedido=ID_PEDIDO)
    assert "o evento não é do pedido enviado (Id do pedido diferente)" in problemas


# --- conferência da assinatura pela porta recebida (T-043) -------------------------------


class ConferidorFalso:
    """Guarda o XML recebido e, se pedido, recusa a assinatura como o adaptador recusaria."""

    def __init__(self, *, recusar: bool):
        self.recusar = recusar
        self.recebidos = []

    def __call__(self, xml: bytes) -> None:
        self.recebidos.append(xml)
        if self.recusar:
            raise ValueError("assinatura não confere")


def test_a_assinatura_e_conferida_pelo_conferidor_recebido(evento, xsd):
    conferidor = ConferidorFalso(recusar=True)
    problemas = dominio_evento.conferir_evento(
        evento, chave=CHAVE, tipo=CANCELAMENTO, xsd=xsd, conferir_assinatura=conferidor
    )
    assert problemas == ["assinatura do evento não confere com o certificado que ele traz"]
    assert conferidor.recebidos == [evento]


def test_conferidor_que_aceita_nao_gera_problema(evento, xsd):
    # O evento alterado só é apontado pela assinatura; quem confere é o conferidor recebido.
    alterado = evento.replace(b"<cMotivo>1</cMotivo>", b"<cMotivo>2</cMotivo>", 1)
    conferidor = ConferidorFalso(recusar=False)
    problemas = dominio_evento.conferir_evento(
        alterado, chave=CHAVE, tipo=CANCELAMENTO, xsd=xsd, conferir_assinatura=conferidor
    )
    assert problemas == []
    assert conferidor.recebidos == [alterado]


def test_a_substituicao_passa_o_conferidor_adiante(xsd):
    evento = gerar_evento(tipo="105102", ch_substituta="1" * 50)
    conferidor = ConferidorFalso(recusar=True)
    problemas = dominio_evento.conferir_substituicao(
        evento,
        chave_substituida=CHAVE,
        chave_substituta="1" * 50,
        xsd=xsd,
        conferir_assinatura=conferidor,
    )
    assert problemas == ["assinatura do evento não confere com o certificado que ele traz"]
    assert conferidor.recebidos == [evento]
