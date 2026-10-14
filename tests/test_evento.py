"""Conferência do evento devolvido pela consulta de eventos (T-028, DEC-051)."""

import pytest

from src.config import XSD_DIR_PADRAO
from src.evento import conferir_evento, localizar_xsd_evento
from tests.evento_ficticio import CANCELAMENTO, gerar_evento
from tests.nfse_ficticia import CHAVE


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
