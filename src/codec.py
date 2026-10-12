"""Empacotamento da DPS para a API: GZip e depois Base64, e o caminho inverso.

Só biblioteca padrão (T-006). As mensagens de erro não trazem o conteúdo recebido.
"""

from __future__ import annotations

import base64
import binascii
import gzip
import zlib


def codificar(xml: bytes) -> str:
    """Comprime os bytes com GZip e devolve o resultado em Base64, numa linha só.

    O cabeçalho GZip vai com `mtime` 0, para que a mesma entrada gere sempre a mesma saída.
    """
    if not isinstance(xml, bytes):
        raise TypeError(f"codificar espera bytes, recebido: {type(xml).__name__}")
    return base64.b64encode(gzip.compress(xml, mtime=0)).decode("ascii")


def decodificar(texto: str) -> bytes:
    """Faz o inverso de `codificar`: Base64 para bytes, depois descompacta o GZip."""
    if not isinstance(texto, str):
        raise TypeError(f"decodificar espera str, recebido: {type(texto).__name__}")
    try:
        comprimido = base64.b64decode(texto, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("não é Base64 válido (alfabeto padrão, sem quebras de linha)") from None
    # gzip.decompress devolve b"" para entrada vazia, que não é um arquivo GZip.
    if not comprimido:
        raise ValueError("não é GZip válido: conteúdo vazio")
    try:
        return gzip.decompress(comprimido)
    except (OSError, EOFError, zlib.error):
        raise ValueError("não é GZip válido: cabeçalho, dados ou CRC incorretos") from None
