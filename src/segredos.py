"""Arquivos que nunca podem ser versionados (INV-03): .env e certificados."""
from __future__ import annotations

from pathlib import PurePosixPath
from typing import Iterable

EXTENSOES = (".pfx", ".p12", ".pem")


def proibidos(caminhos: Iterable[str]) -> list[str]:
    """Dos caminhos dados (como em `git ls-files`), devolve os que são segredo."""
    achados = []
    for caminho in caminhos:
        nome = PurePosixPath(caminho.replace("\\", "/")).name
        if nome == ".env" or nome.lower().endswith(EXTENSOES):
            achados.append(caminho)
    return achados
