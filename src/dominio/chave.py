"""Leitura da chave de acesso da NFS-e, 50 dígitos (T-043).

Anexo I, Id da NFS-e (docs/SOURCES.md): município (7), ambiente gerador (1), tipo de
inscrição federal (1), inscrição federal (14), número (13), ano e mês (4), código (9), DV (1).
As funções só recortam: o formato da chave é conferido por quem a recebe.
"""

from __future__ import annotations

TIPO_INSCRICAO_CNPJ = "2"


def municipio(chave: str) -> str:
    """Código IBGE do município emissor: posições 1 a 7."""
    return chave[0:7]


def tipo_inscricao(chave: str) -> str:
    """Tipo de inscrição federal do emitente (2 = CNPJ): posição 9."""
    return chave[8]


def cnpj_do_emitente(chave: str) -> str:
    """Inscrição federal do emitente: posições 10 a 23."""
    return chave[9:23]
