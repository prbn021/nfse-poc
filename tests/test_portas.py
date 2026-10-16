"""Portas da aplicação (T-042, DEC-075): o cliente da SEFIN cumpre os Protocols dos serviços."""

import inspect
import typing

import pytest

from src import cancelamento, emissao
from src.aplicacao.portas import ConferidorAssinatura, SefinEmissao, SefinEventos
from src.assinatura import conferir_assinatura_do_sistema
from src.client import ClienteNfse


def _metodos(porta) -> list[str]:
    return sorted(
        nome for nome, valor in vars(porta).items() if inspect.isfunction(valor) and nome[0] != "_"
    )


@pytest.mark.parametrize(
    ("porta", "metodos"),
    [
        (SefinEmissao, ["chave_da_dps", "emitir", "obter_nfse"]),
        (SefinEventos, ["consultar_evento", "registrar_evento"]),
    ],
)
def test_a_porta_tem_so_o_que_o_servico_usa(porta, metodos):
    assert _metodos(porta) == metodos


@pytest.mark.parametrize("porta", [SefinEmissao, SefinEventos])
def test_o_cliente_cumpre_a_porta(porta):
    for nome in _metodos(porta):
        esperada = inspect.signature(getattr(porta, nome))
        real = inspect.signature(getattr(ClienteNfse, nome))
        assert [(p.name, p.annotation) for p in real.parameters.values()] == [
            (p.name, p.annotation) for p in esperada.parameters.values()
        ], nome
        assert real.return_annotation == esperada.return_annotation, nome


def test_os_servicos_recebem_as_portas():
    assert typing.get_type_hints(emissao.emitir)["cliente"] is SefinEmissao
    assert typing.get_type_hints(cancelamento.cancelar)["cliente"] is SefinEventos


def test_os_servicos_recebem_o_conferidor_da_assinatura():
    # T-043: a conferência da assinatura do sistema chega pela porta, não por import.
    assert typing.get_type_hints(emissao.emitir)["conferir_assinatura"] is ConferidorAssinatura
    assert (
        typing.get_type_hints(cancelamento.cancelar)["conferir_assinatura"] is ConferidorAssinatura
    )


def test_o_adaptador_de_assinatura_cumpre_o_conferidor():
    esperada = inspect.signature(ConferidorAssinatura.__call__)
    real = inspect.signature(conferir_assinatura_do_sistema)
    assert [(p.name, p.annotation) for p in real.parameters.values()] == [
        (p.name, p.annotation) for p in esperada.parameters.values() if p.name != "self"
    ]
    assert real.return_annotation == esperada.return_annotation
