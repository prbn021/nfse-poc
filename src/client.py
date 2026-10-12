"""Cliente HTTP com mTLS para a API da SEFIN Nacional em produção restrita (T-015, DEC-031).

Único módulo de src/ e de scripts/ que faz I/O de rede (B-2). Abre a conexão com o
certificado do emitente, envia a DPS assinada (`POST /nfse`) e consulta DPS e NFS-e (T-007,
DEC-036). Não repete pedidos: a política de envio fica em `src/emissao.py`.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import ssl
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import httpx
from cryptography.hazmat.primitives import serialization

from src.certificado import Certificado
from src.codec import codificar, decodificar
from src.config import Config
from src.erros import MensagemApi, RejeicaoApi, RespostaInesperada
from src.nfse import NfseEmitida

# Só hosts da produção restrita (docs/SPEC.md §6). Produção é recusada (INV-02, DEC-002).
SUFIXO_HOST = ".producaorestrita.nfse.gov.br"
TEMPO_LIMITE = 30.0  # segundos

_ID_DPS = re.compile(r"DPS\d{42}")
_CHAVE = re.compile(r"\d{50}")
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


# APIs que o cliente alcança: nome -> (atributo de Config, variável do .env).
APIS = {"sefin": ("sefin_url", "NFSE_SEFIN_URL"), "adn": ("adn_url", "NFSE_ADN_URL")}


def _conferir_destino(config: Config, api: str) -> str:
    """INV-02: só a produção restrita, por ambiente e por URL. Devolve a URL base da API."""
    if api not in APIS:
        raise ValueError(f"api desconhecida: {api!r} (use {', '.join(APIS)})")
    if config.ambiente != "homologacao":
        raise ValueError(
            f"ambiente {config.ambiente!r} recusado: só produção restrita (INV-02, DEC-002)"
        )
    atributo, variavel = APIS[api]
    url = getattr(config, atributo)
    partes = urlsplit(url)
    host = partes.hostname or ""
    if (
        partes.scheme != "https"
        or not host.endswith(SUFIXO_HOST)
        or partes.username is not None
        or partes.query
        or partes.fragment
    ):
        raise ValueError(
            f"{variavel} {url!r} recusada: só https://*{SUFIXO_HOST} (INV-02, DEC-002)"
        )
    return url


class ClienteNfse:
    """Conexão mTLS com a SEFIN Nacional ou, com `api="adn"`, com o ADN (T-026).

    Use com `with`, para fechar a conexão.
    """

    def __init__(
        self,
        config: Config,
        cert: Certificado,
        *,
        api: str = "sefin",
        transporte: httpx.BaseTransport | None = None,
    ) -> None:
        self.api = api
        self.base_url = _conferir_destino(config, api)
        # `transporte` existe para os testes, que simulam o servidor sem rede.
        self._http = httpx.Client(
            base_url=self.base_url + "/",
            verify=contexto_tls(cert),
            timeout=TEMPO_LIMITE,
            transport=transporte,
            trust_env=False,
        )

    @property
    def sefin_url(self) -> str:
        """URL base em uso; o nome vem da T-015, quando só havia a SEFIN."""
        return self.base_url

    def __repr__(self) -> str:
        return f"ClienteNfse({APIS[self.api][0]}={self.base_url!r})"

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

    def emitir(self, dps_assinada: bytes) -> NfseEmitida:
        """`POST /nfse` com a DPS assinada em GZip+Base64; devolve a NFS-e gerada.

        Não repete o envio em caso de falha: quem decide é `src/emissao.py`.
        """
        if not isinstance(dps_assinada, bytes):
            raise TypeError(f"emitir espera bytes, recebido: {type(dps_assinada).__name__}")
        resposta = self._pedir(
            "POST", "nfse", corpo_json={"dpsXmlGZipB64": codificar(dps_assinada)}
        )
        with _anexar_corpo(resposta):
            if resposta.status == 201:
                corpo = _objeto_json(resposta)
                return NfseEmitida(
                    chave=_chave(resposta.status, corpo),
                    id_dps=_id_dps(resposta.status, corpo),
                    xml=_nfse_xml(resposta.status, corpo),
                    alertas=_mensagens(resposta.status, corpo.get("alertas"), "alertas"),
                )
            if resposta.status in (400, 403, 500):
                raise _rejeicao(resposta)
            raise RespostaInesperada(
                resposta.status, f"HTTP {resposta.status} não previsto no envio"
            )

    def chave_da_dps(self, id_dps: str) -> str | None:
        """`GET /dps/{id}`: a chave de acesso da NFS-e gerada a partir da DPS, ou None."""
        if not _ID_DPS.fullmatch(id_dps):
            raise ValueError("Id da DPS fora do formato: 'DPS' seguido de 42 dígitos (INV-04)")
        resposta = self._pedir("GET", f"dps/{id_dps}")
        with _anexar_corpo(resposta):
            if resposta.status == 200:
                return _chave(resposta.status, _objeto_json(resposta))
            if resposta.status == 404:
                return None
            if resposta.status == 400:
                raise _rejeicao(resposta)
            raise RespostaInesperada(
                resposta.status, f"HTTP {resposta.status} não previsto na consulta"
            )

    def obter_nfse(self, chave: str) -> bytes:
        """`GET /nfse/{chave}`: o XML da NFS-e, já decodificado."""
        if not _CHAVE.fullmatch(chave):
            raise ValueError("chave de acesso fora do formato: 50 dígitos")
        resposta = self._pedir("GET", f"nfse/{chave}")
        with _anexar_corpo(resposta):
            if resposta.status == 200:
                return _nfse_xml(resposta.status, _objeto_json(resposta))
            if resposta.status in (400, 401, 403, 404):
                raise _rejeicao(resposta)
            raise RespostaInesperada(
                resposta.status, f"HTTP {resposta.status} não previsto na consulta"
            )

    def _pedir(self, metodo: str, caminho: str, *, corpo_json: dict | None = None) -> Resposta:
        try:
            resposta = self._http.request(metodo, caminho, json=corpo_json)
        except httpx.HTTPError as erro:
            mensagem = f"{type(erro).__name__}: {erro}"
            falha = True
        else:
            falha = False
        if falha:
            raise ErroConexao(mensagem)
        tipo = resposta.headers.get("content-type", "").split(";")[0].strip()
        return Resposta(status=resposta.status_code, tipo=tipo, corpo=resposta.content)


# Leitura das respostas JSON da API (docs/SOURCES.md, especificação da SEFIN). Nenhuma
# mensagem de erro daqui traz o corpo bruto da resposta.


def _objeto_json(resposta: Resposta) -> dict:
    """O corpo como dicionário com as chaves em minúsculas.

    A especificação usa camelCase, mas a SEFIN real respondeu em PascalCase (DEC-037,
    DEC-039): os campos são lidos sem distinguir maiúsculas.
    """
    try:
        corpo = json.loads(resposta.corpo)
    except ValueError:
        raise RespostaInesperada(resposta.status, "corpo não é JSON") from None
    if not isinstance(corpo, dict):
        raise RespostaInesperada(resposta.status, "corpo não é um objeto JSON")
    return {chave.lower(): valor for chave, valor in corpo.items() if isinstance(chave, str)}


def _chave(status: int, corpo: dict) -> str:
    chave = corpo.get("chaveacesso")
    if not isinstance(chave, str) or not _CHAVE.fullmatch(chave):
        raise RespostaInesperada(status, "chaveAcesso ausente ou fora do formato de 50 dígitos")
    return chave


def _id_dps(status: int, corpo: dict) -> str:
    id_dps = corpo.get("iddps")
    if not isinstance(id_dps, str) or not _ID_DPS.fullmatch(id_dps):
        raise RespostaInesperada(status, "idDps ausente ou fora do formato")
    return id_dps


def _nfse_xml(status: int, corpo: dict) -> bytes:
    texto = corpo.get("nfsexmlgzipb64")
    if not isinstance(texto, str):
        raise RespostaInesperada(status, "nfseXmlGZipB64 ausente")
    try:
        return decodificar(texto)
    except ValueError as erro:
        motivo = f"nfseXmlGZipB64 inválido: {erro}"
    raise RespostaInesperada(status, motivo)


def _texto(valor: object) -> str | None:
    if valor is None or isinstance(valor, (dict, list)):
        return None
    return str(valor)


def _mensagem(item: object) -> MensagemApi:
    """Lê um `MensagemProcessamento` com tolerância: a primeira transmissão real (2026-10-12)
    devolveu itens fora do formato da especificação (DEC-037). Nada aqui é descartado sem aviso:
    o que não se reconhece vira código "?", e a resposta inteira é salva por quem chamou.
    """
    if not isinstance(item, dict):
        return MensagemApi("?", _texto(item) or "item vazio")
    # Sem distinguir maiúsculas: `codigo`, `Codigo` e `CODIGO` valem igual.
    campos = {chave.lower(): valor for chave, valor in item.items() if isinstance(chave, str)}
    codigo = _texto(campos.get("codigo"))
    descricao = _texto(campos.get("descricao"))
    complemento = _texto(campos.get("complemento"))
    if codigo is None and descricao is None:
        return MensagemApi("?", "item sem codigo nem descricao", complemento)
    return MensagemApi(codigo or "?", descricao or "", complemento)


def _mensagens(status: int, lista: object, campo: str) -> tuple[MensagemApi, ...]:
    if lista is None:
        return ()
    if not isinstance(lista, list):
        raise RespostaInesperada(status, f"{campo} não é uma lista")
    return tuple(_mensagem(item) for item in lista)


@contextmanager
def _anexar_corpo(resposta: Resposta):
    """Põe o corpo bruto da resposta nas exceções da API, para quem chamou poder salvá-lo.

    O corpo fica num atributo, nunca na mensagem.
    """
    try:
        yield
    except (RejeicaoApi, RespostaInesperada) as erro:
        erro.corpo = resposta.corpo
        raise


def _rejeicao(resposta: Resposta) -> RejeicaoApi:
    corpo = _objeto_json(resposta)
    # O envio devolve uma lista `erros`; as consultas, um objeto `erro` só.
    if "erros" in corpo:
        mensagens = _mensagens(resposta.status, corpo["erros"], "erros")
    else:
        mensagens = _mensagens(resposta.status, [corpo["erro"]] if "erro" in corpo else [], "erro")
    id_dps = corpo.get("iddps")
    return RejeicaoApi(resposta.status, id_dps if isinstance(id_dps, str) else None, mensagens)
