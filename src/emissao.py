"""Envio de uma DPS assinada sem risco de nota em dobro (T-007, DEC-036).

`POST /nfse` não é idempotente: reenviar a mesma DPS gera rejeição E0014 ou, se a primeira
tentativa tiver sido processada sem resposta, deixa a dúvida sobre a nota. Por isso:

- antes de enviar, consulta `GET /dps/{id}`; se já existe NFS-e para o Id, não envia;
- envia uma vez só, sem retry automático;
- se a conexão cair, a resposta vier ilegível ou com erro interno (5xx), consulta de novo: se
  a nota existe, baixa; se não, passa o erro adiante (na queda, dizendo que pode reenviar);
  se nem a consulta responde, o envio fica incerto e quem decide é a pessoa (DEC-039).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from lxml import etree

from src.client import ErroConexao
from src.dps import NS
from src.erros import RejeicaoApi, RespostaInesperada
from src.nfse import NfseEmitida, conferir_nfse

_DS = "http://www.w3.org/2000/09/xmldsig#"


class Cliente(Protocol):
    def chave_da_dps(self, id_dps: str) -> str | None: ...
    def emitir(self, dps_assinada: bytes) -> NfseEmitida: ...
    def obter_nfse(self, chave: str) -> bytes: ...


class DpsJaEmitida(Exception):
    def __init__(self, id_dps: str, chave: str):
        self.id_dps = id_dps
        self.chave = chave
        super().__init__(
            f"já existe NFS-e para esta DPS (chave {chave}); não enviada, para não cair em E0014. "
            "Use outro número de DPS"
        )


class EnvioIncerto(Exception):
    """A conexão caiu depois do envio e a consulta também falhou: não se sabe se a nota existe."""

    def __init__(self, id_dps: str):
        self.id_dps = id_dps
        super().__init__(
            "a conexão caiu durante o envio e a consulta seguinte também falhou: não se sabe se "
            "a NFS-e foi gerada. Não reenvie; consulte a DPS de novo mais tarde (GET /dps/{id})"
        )


@dataclass(frozen=True)
class Resultado:
    nfse: NfseEmitida
    problemas: list[str] = field(default_factory=list)  # da conferência; a nota já existe
    recuperada: bool = False  # True: obtida pela consulta depois de uma falha no envio
    # A falha que levou à recuperação (queda, resposta ilegível ou 5xx), para quem chamou
    # mostrar a causa e salvar a resposta bruta (DEC-044).
    falha: Exception | None = field(default=None, repr=False, compare=False)


def _id_da_dps_assinada(xml: bytes) -> str:
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    try:
        raiz = etree.fromstring(xml, parser)
    except etree.XMLSyntaxError:
        raiz = None
    inf = raiz.find(f"{{{NS}}}infDPS") if raiz is not None else None
    id_dps = inf.get("Id") if inf is not None else None
    if not id_dps:
        raise ValueError("DPS sem infDPS com Id: nada enviado")
    if raiz.find(f"{{{_DS}}}Signature") is None:
        raise ValueError("a DPS precisa estar assinada antes do envio (E0717): nada enviado")
    return id_dps


def emitir(cliente: Cliente, dps_assinada: bytes, xsd_nfse: Path) -> Resultado:
    """Envia a DPS uma vez e confere a NFS-e devolvida."""
    id_dps = _id_da_dps_assinada(dps_assinada)

    chave = cliente.chave_da_dps(id_dps)
    if chave is not None:
        raise DpsJaEmitida(id_dps, chave)

    recuperada = False
    falha = None
    try:
        nfse = cliente.emitir(dps_assinada)
    except (ErroConexao, RespostaInesperada) as erro:
        falha = erro
    except RejeicaoApi as erro:
        # 400 e 403 são recusas; 500 é falha de processamento, que pode ter gerado a nota.
        if erro.status < 500:
            raise
        falha = erro
    if falha is not None:
        # A nota pode existir: a resposta não chegou, veio ilegível ou com erro interno.
        try:
            chave = cliente.chave_da_dps(id_dps)
        except ErroConexao:
            chave = None
            incerto = True
        else:
            incerto = False
        if incerto:
            raise EnvioIncerto(id_dps)
        if chave is None:
            if isinstance(falha, ErroConexao):
                raise ErroConexao(
                    f"{falha}; a consulta seguinte mostrou que nenhuma NFS-e foi gerada: a DPS "
                    "pode ser enviada de novo"
                )
            raise falha
        nfse = NfseEmitida(chave=chave, id_dps=id_dps, xml=cliente.obter_nfse(chave))
        recuperada = True

    # Sem `id_dps` na resposta (DEC-045), a conferência compara a DPS embutida na nota.
    if nfse.id_dps is not None and nfse.id_dps != id_dps:
        raise RespostaInesperada(201, "idDps devolvido não é o da DPS enviada")
    problemas = conferir_nfse(nfse.xml, chave=nfse.chave, id_dps=id_dps, xsd=xsd_nfse)
    return Resultado(nfse=nfse, problemas=problemas, recuperada=recuperada, falha=falha)
