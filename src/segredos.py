"""Arquivos que nunca podem ser versionados.

São eles: .env, certificados e arquivos de emitente (INV-03) e referências privadas.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import PurePosixPath

EXTENSOES = (".pfx", ".p12", ".pem")

# docs/referencia guarda notas de clientes e outros arquivos com dados reais.
# Só a documentação oficial, em gov-docs, pode ser versionada (T-017).
REFERENCIA = PurePosixPath("docs/referencia")
REFERENCIA_PUBLICA = REFERENCIA / "gov-docs"

# emitentes/ guarda a senha do certificado de cada emitente. Só o exemplo, com dados
# fictícios, pode ser versionado (T-019).
EMITENTES = PurePosixPath("emitentes")
EMITENTE_EXEMPLO = EMITENTES / "exemplo.toml"


def proibidos(caminhos: Iterable[str]) -> list[str]:
    """Dos caminhos dados (como em `git ls-files`), devolve os que não podem ser versionados."""
    achados = []
    for caminho in caminhos:
        posix = PurePosixPath(caminho.replace("\\", "/"))
        nome = posix.name
        privado = REFERENCIA in posix.parents and REFERENCIA_PUBLICA not in posix.parents
        emitente = EMITENTES in posix.parents and posix != EMITENTE_EXEMPLO
        if nome == ".env" or nome.lower().endswith(EXTENSOES) or privado or emitente:
            achados.append(caminho)
    return achados
