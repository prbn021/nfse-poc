"""Cópia local dos XSDs oficiais, só para validação offline.

O XSD oficial v1.01 traz um padrão com ^ e $ (TSSerieDPS). Em XML Schema as expressões
já são ancoradas e esses dois caracteres são literais, então o lxml/libxml2 rejeita
qualquer série. Os oficiais nunca são editados: geramos uma cópia sem as âncoras.
"""
from __future__ import annotations

import re
from pathlib import Path

_PATTERN = re.compile(rb'(<\w+:pattern\s+value=")([^"]*)(")')


def _sem_ancoras(m: re.Match[bytes]) -> bytes:
    valor = m.group(2)
    if valor.startswith(b"^"):
        valor = valor[1:]
    if valor.endswith(b"$") and not valor.endswith(rb"\$"):
        valor = valor[:-1]
    return m.group(1) + valor + m.group(3)


def remover_ancoras(xsd: bytes) -> bytes:
    """Tira ^ do início e $ do fim dos xs:pattern. Em bytes, para não mexer em codificação nem em quebras de linha."""
    return _PATTERN.sub(_sem_ancoras, xsd)


def dir_local(xsd_dir: Path) -> Path:
    """Pasta da cópia local, ao lado da oficial: schemas/1.01 -> schemas/1.01-local."""
    xsd_dir = Path(xsd_dir)
    return xsd_dir.with_name(xsd_dir.name + "-local")


def preparar_copia_local(origem: Path, destino: Path | None = None) -> Path:
    """(Re)gera em `destino` a cópia dos .xsd de `origem` sem as âncoras. Retorna `destino`."""
    origem = Path(origem)
    destino = Path(destino) if destino is not None else dir_local(origem)
    if destino.resolve() == origem.resolve():
        raise ValueError(f"destino não pode ser a pasta dos XSDs oficiais: {origem}")
    destino.mkdir(parents=True, exist_ok=True)
    for f in origem.glob("*.xsd"):
        (destino / f.name).write_bytes(remover_ancoras(f.read_bytes()))
    return destino
