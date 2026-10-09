"""Cliente HTTP com mTLS para a API da SEFIN Nacional em produção restrita (T-015, DEC-031).

Único módulo de src/ e de scripts/ que faz I/O de rede (B-2). Versão mínima: abre a conexão
com o certificado do emitente e faz consultas que não emitem nem alteram nada. Envio da DPS,
tratamento dos erros da API e retries ficam para a T-007.
"""

from __future__ import annotations

import os
import re
import secrets
import ssl
import tempfile
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import httpx
from cryptography.hazmat.primitives import serialization

from src.certificado import Certificado
from src.config import Config

# Só hosts da produção restrita (docs/SPEC.md §6). Produção é recusada (INV-02, DEC-002).
SUFIXO_HOST = ".producaorestrita.nfse.gov.br"
TEMPO_LIMITE = 30.0  # segundos

_ID_DPS = re.compile(r"DPS\d{42}")
_CAMINHO = re.compile(r"[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*")


class ErroConexao(Exception):
    """Falha de rede ou de TLS: a requisição não recebeu resposta HTTP."""


@dataclass(frozen=True)
class Resposta:
    status: int
    tipo: str  # Content-Type, sem parâmetros
    corpo: bytes = field(repr=False)


def contexto_tls(cert: Certificado) -> ssl.SSLContext:
    """Contexto TLS que apresenta o certificado do emitente ao servidor.

    O `ssl` só carrega a chave a partir de arquivo. Ela vai a um arquivo temporário cifrado
    com uma senha aleatória que só existe em memória, apagado logo depois da carga (DEC-031).
    """
    senha = secrets.token_urlsafe(32).encode("ascii")
    pem = cert.chave.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.BestAvailableEncryption(senha),
    )
    for certificado in (cert.certificado, *cert.cadeia):
        pem += certificado.public_bytes(serialization.Encoding.PEM)

    contexto = ssl.create_default_context()
    descritor, caminho = tempfile.mkstemp(suffix=".pem")
    falhou = False
    try:
        # Fechado antes de carregar: no Windows, um arquivo aberto não pode ser reaberto.
        with os.fdopen(descritor, "wb") as arquivo:
            arquivo.write(pem)
        try:
            contexto.load_cert_chain(caminho, password=senha)
        except ssl.SSLError:
            falhou = True
    finally:
        os.remove(caminho)
    # Levantado fora do `except`, para a exceção do ssl não ficar encadeada (DEC-030).
    if falhou:
        raise ValueError("não foi possível carregar o certificado no TLS")
    return contexto


def _conferir_destino(config: Config) -> None:
    """INV-02: só a produção restrita, por ambiente e por URL."""
    if config.ambiente != "homologacao":
        raise ValueError(
            f"ambiente {config.ambiente!r} recusado: só produção restrita (INV-02, DEC-002)"
        )
    partes = urlsplit(config.sefin_url)
    host = partes.hostname or ""
    if (
        partes.scheme != "https"
        or not host.endswith(SUFIXO_HOST)
        or partes.username is not None
        or partes.query
        or partes.fragment
    ):
        raise ValueError(
            f"NFSE_SEFIN_URL {config.sefin_url!r} recusada: só https://*{SUFIXO_HOST} "
            "(INV-02, DEC-002)"
        )


class ClienteNfse:
    """Conexão mTLS com a SEFIN Nacional. Use com `with`, para fechar a conexão."""

    def __init__(
        self,
        config: Config,
        cert: Certificado,
        *,
        transporte: httpx.BaseTransport | None = None,
    ) -> None:
        _conferir_destino(config)
        self.sefin_url = config.sefin_url
        # `transporte` existe para os testes, que simulam o servidor sem rede.
        self._http = httpx.Client(
            base_url=self.sefin_url + "/",
            verify=contexto_tls(cert),
            timeout=TEMPO_LIMITE,
            transport=transporte,
            trust_env=False,
        )

    def __repr__(self) -> str:
        return f"ClienteNfse(sefin_url={self.sefin_url!r})"

    def __enter__(self) -> ClienteNfse:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    def consultar_dps(self, id_dps: str) -> Resposta:
        """`HEAD /dps/{id}`: diz se a DPS existe, sem emitir nada."""
        if not _ID_DPS.fullmatch(id_dps):
            raise ValueError("Id da DPS fora do formato: 'DPS' seguido de 42 dígitos (INV-04)")
        return self._pedir("HEAD", f"dps/{id_dps}")

    def obter(self, caminho: str) -> Resposta:
        """GET de um caminho relativo à URL base da SEFIN (ex.: `docs/index`)."""
        if not _CAMINHO.fullmatch(caminho) or {".", ".."} & set(caminho.split("/")):
            raise ValueError(f"caminho recusado: {caminho!r} (relativo à URL base, sem '.' e '..')")
        return self._pedir("GET", caminho)

    def _pedir(self, metodo: str, caminho: str) -> Resposta:
        try:
            resposta = self._http.request(metodo, caminho)
        except httpx.HTTPError as erro:
            mensagem = f"{type(erro).__name__}: {erro}"
            falha = True
        else:
            falha = False
        if falha:
            raise ErroConexao(mensagem)
        tipo = resposta.headers.get("content-type", "").split(";")[0].strip()
        return Resposta(status=resposta.status_code, tipo=tipo, corpo=resposta.content)
