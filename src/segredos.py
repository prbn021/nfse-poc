"""Arquivos que nunca podem ser versionados: .env e certificados (INV-03) e referências com dados reais."""
from __future__ import annotations

from pathlib import PurePosixPath
from typing import Iterable

EXTENSOES = (".pfx", ".p12", ".pem")

# docs/referencia guarda notas de clientes e outros arquivos com dados reais.
# Só a documentação oficial, em gov-docs, pode ser versionada (T-017).
REFERENCIA = PurePosixPath("docs/referencia")
REFERENCIA_PUBLICA = REFERENCIA / "gov-docs"


def proibidos(caminhos: Iterable[str]) -> list[str]:
    """Dos caminhos dados (como em `git ls-files`), devolve os que não podem ser versionados."""
    achados = []
    for caminho in caminhos:
        posix = PurePosixPath(caminho.replace("\\", "/"))
        nome = posix.name
        privado = REFERENCIA in posix.parents and REFERENCIA_PUBLICA not in posix.parents
        if nome == ".env" or nome.lower().endswith(EXTENSOES) or privado:
            achados.append(caminho)
    return achados
