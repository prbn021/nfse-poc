"""O que a conferência da NFS-e e do evento pede de fora: conferir a assinatura (T-043).

A assinatura do sistema nacional é conferida com criptografia (signxml), que o domínio não
importa (B-4). `conferir_nfse` e `conferir_evento` recebem quem confere; o adaptador é
`src.assinatura.conferir_assinatura_do_sistema`. A porta é declarada aqui, e não em
`src/aplicacao/portas.py`, porque o domínio não importa a aplicação; `portas` a reexporta.
"""

from __future__ import annotations

from typing import Protocol


class ConferidorAssinatura(Protocol):
    """Confere a assinatura do XML com o certificado que ele traz.

    Levanta `ValueError` quando a assinatura não confere; não devolve nada quando confere.
    """

    def __call__(self, xml: bytes) -> None: ...
