"""Envio do pedido de cancelamento (101101) sem reenvio às cegas (T-030).

`POST /nfse/{chave}/eventos` não é idempotente: depois de um cancelamento, a NFS-e não aceita
outro evento, e um segundo pedido volta com E0840 (Anexo II, aba `RN EVENTOSxEVENTOS`). O
cancelamento só acontece uma vez, então o evento é sempre o de número sequencial 1. Por isso,
como em `src/emissao.py`:

- antes de enviar, consulta o evento 101101 da nota; se ele existe, não envia;
- envia uma vez só, sem retry automático;
- se a conexão cair ou a resposta vier fora do formato (inclui 5xx), consulta de novo: se o
  evento existe, é ele o resultado; se não, passa o erro adiante (na queda, dizendo que pode
  reenviar); se nem a consulta responde, o cancelamento fica incerto e quem decide é a pessoa.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from src.aplicacao.portas import SefinEventos
from src.dps import NS
from src.erros import ErroConexao, RespostaInesperada
from src.evento import CANCELAMENTO, conferir_evento

_DS = "http://www.w3.org/2000/09/xmldsig#"
_SEQ = 1  # o cancelamento é evento único: nSeqEvento 001 (Anexo II)


class NotaJaCancelada(Exception):
    def __init__(self, chave: str, evento: bytes):
        self.chave = chave
        self.evento = evento
        super().__init__(
            f"a NFS-e {chave} já tem evento de cancelamento; pedido não enviado, para não "
            "cair em E0840"
        )


class CancelamentoIncerto(Exception):
    """A conexão caiu depois do envio e a consulta também falhou: não se sabe se a nota foi
    cancelada."""

    def __init__(self, chave: str):
        self.chave = chave
        super().__init__(
            "a conexão caiu durante o envio e a consulta seguinte também falhou: não se sabe se "
            "a NFS-e foi cancelada. Não reenvie; consulte o evento mais tarde "
            "(consultar_nfse.py --evento 101101)"
        )


@dataclass(frozen=True)
class Resultado:
    evento: bytes = field(repr=False)
    problemas: list[str] = field(default_factory=list)  # da conferência; o evento já existe
    recuperado: bool = False  # True: obtido pela consulta depois de uma falha no envio
    # A falha que levou à recuperação, para quem chamou mostrar a causa e salvar a resposta.
    falha: Exception | None = field(default=None, repr=False, compare=False)


def _dados_do_pedido(xml: bytes) -> tuple[str, str]:
    """Id e chave do pedido assinado; recusa o que não pode ser enviado."""
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    try:
        raiz = etree.fromstring(xml, parser)
    except (etree.XMLSyntaxError, ValueError):
        raiz = None
    if raiz is None or raiz.tag != f"{{{NS}}}pedRegEvento":
        raise ValueError("o pedido não é um pedRegEvento em XML: nada enviado")
    inf = raiz.find(f"{{{NS}}}infPedReg")
    id_pedido = inf.get("Id") if inf is not None else None
    chave = inf.findtext(f"{{{NS}}}chNFSe") if inf is not None else None
    if not chave or id_pedido != f"PRE{chave}{CANCELAMENTO}":
        raise ValueError(
            'Id do pedido não é "PRE" + chNFSe + 101101 (E1827): só o cancelamento é '
            "enviado; nada enviado"
        )
    if raiz.find(f"{{{_DS}}}Signature") is None:
        raise ValueError("o pedido precisa estar assinado antes do envio (E1989): nada enviado")
    return id_pedido, chave


def cancelar(cliente: SefinEventos, pedido_assinado: bytes, xsd_evento: Path) -> Resultado:
    """Envia o pedido de cancelamento uma vez e confere o evento devolvido."""
    id_pedido, chave = _dados_do_pedido(pedido_assinado)

    existente = cliente.consultar_evento(chave, CANCELAMENTO, _SEQ)
    if existente is not None:
        raise NotaJaCancelada(chave, existente)

    recuperado = False
    falha = None
    try:
        evento = cliente.registrar_evento(chave, pedido_assinado)
    except (ErroConexao, RespostaInesperada) as erro:
        falha = erro
    if falha is not None:
        # O evento pode ter sido registrado: a resposta não chegou ou veio ilegível.
        try:
            evento = cliente.consultar_evento(chave, CANCELAMENTO, _SEQ)
        except ErroConexao:
            evento = None
            incerto = True
        else:
            incerto = False
        if incerto:
            raise CancelamentoIncerto(chave)
        if evento is None:
            if isinstance(falha, ErroConexao):
                raise ErroConexao(
                    f"{falha}; a consulta seguinte mostrou que nenhum evento foi registrado: o "
                    "pedido pode ser enviado de novo"
                )
            raise falha
        recuperado = True

    problemas = conferir_evento(
        evento, chave=chave, tipo=CANCELAMENTO, xsd=xsd_evento, id_pedido=id_pedido
    )
    return Resultado(evento=evento, problemas=problemas, recuperado=recuperado, falha=falha)
