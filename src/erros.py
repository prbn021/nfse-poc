"""Erros devolvidos pela API da SEFIN Nacional (T-007).

A API responde erros com uma lista de `MensagemProcessamento` (`codigo`, `descricao`,
`complemento`), conforme a especificação servida por ela (docs/SOURCES.md). As mensagens
destas exceções nunca trazem o corpo bruto da resposta.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MensagemApi:
    codigo: str
    descricao: str
    complemento: str | None = None

    def __str__(self) -> str:
        texto = f"{self.codigo}: {self.descricao}"
        return f"{texto} ({self.complemento})" if self.complemento else texto


class RejeicaoApi(Exception):
    """A SEFIN respondeu com erro (400, 403, 500 no envio; 400 nas consultas)."""

    def __init__(self, status: int, id_dps: str | None, mensagens: tuple[MensagemApi, ...]):
        self.status = status
        self.id_dps = id_dps
        self.mensagens = mensagens
        lista = "; ".join(str(m) for m in mensagens) or "sem mensagens"
        super().__init__(f"SEFIN recusou (HTTP {status}): {lista}")


class RespostaInesperada(Exception):
    """A resposta não segue o formato da especificação da API."""

    def __init__(self, status: int, motivo: str):
        self.status = status
        self.motivo = motivo
        super().__init__(f"resposta inesperada da SEFIN (HTTP {status}): {motivo}")
