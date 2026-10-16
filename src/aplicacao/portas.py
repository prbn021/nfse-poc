"""Portas dos serviços de aplicação (T-042, DEC-075).

Cada porta descreve só o que um serviço pede da SEFIN; `src.client.ClienteNfse` cumpre as duas
(`tests/test_portas.py`). As falhas chegam como as exceções de `src/dominio/erros.py`.
`ConferidorAssinatura` é declarada no domínio, que a usa e não pode importar daqui, e
reexportada aqui com as demais (T-043, DEC-078).
"""

from __future__ import annotations

from typing import Protocol

from src.dominio.conferencia import ConferidorAssinatura
from src.dominio.nfse import NfseEmitida

__all__ = ["ConferidorAssinatura", "SefinEmissao", "SefinEventos"]


class SefinEmissao(Protocol):
    """O que `src/emissao.py` usa: consulta da DPS, envio e download da NFS-e."""

    def chave_da_dps(self, id_dps: str) -> str | None: ...
    def emitir(self, dps_assinada: bytes) -> NfseEmitida: ...
    def obter_nfse(self, chave: str) -> bytes: ...


class SefinEventos(Protocol):
    """O que `src/cancelamento.py` usa: consulta e registro de eventos da NFS-e."""

    def consultar_evento(self, chave: str, tipo: str, seq: int) -> bytes | None: ...
    def registrar_evento(self, chave: str, pedido_assinado: bytes) -> bytes: ...
