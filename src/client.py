"""Cliente HTTP com mTLS para a API da SEFIN Nacional em produção restrita (T-015, DEC-031).

Único módulo de src/ e de scripts/ que faz I/O de rede (B-2). Abre a conexão com o
certificado do emitente, envia a DPS assinada (`POST /nfse`) e consulta DPS e NFS-e (T-007,
DEC-036), e registra eventos da NFS-e (T-030). Não repete pedidos: a política de envio fica em
`src/emissao.py` e `src/cancelamento.py`.
"""

from __future__ import annotations

import base64
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
from lxml import etree

from src.certificado import Certificado
from src.codec import codificar, decodificar
from src.config import Config
from src.dominio.dps import NS
from src.dominio.erros import ErroConexao, MensagemApi, RejeicaoApi, RespostaInesperada
from src.dominio.nfse import NfseEmitida

# Só hosts da produção restrita (docs/SPEC.md §6). Produção é recusada (INV-02, DEC-002).
SUFIXO_HOST = ".producaorestrita.nfse.gov.br"
TEMPO_LIMITE = 30.0  # segundos

_ID_DPS = re.compile(r"DPS\d{42}")
_CHAVE = re.compile(r"\d{50}")
_MUNICIPIO = re.compile(r"\d{7}")
_TIPO_EVENTO = re.compile(r"[0-9]{6}")  # código do evento, Anexo II (ex.: 101101)
# 9 dígitos (cTribNac + desdobramento) ou o mesmo pontuado, como no guia do painel municipal.
_CODIGO_SERVICO = re.compile(r"\d{9}|\d{2}\.\d{2}\.\d{2}\.\d{3}")
_PARAMETRIZACAO = "parametrizacao"  # caminho da API de parâmetros municipais no ADN
_CAMINHO = re.compile(r"[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*")


@dataclass(frozen=True)
class Resposta:
    status: int
    tipo: str  # Content-Type, sem parâmetros
    corpo: bytes = field(repr=False)


@dataclass(frozen=True)
class ConsultaParametros:
    """Resposta de uma consulta de parâmetros municipais no ADN (T-026)."""

    status: int
    corpo: dict = field(repr=False)  # chaves do primeiro nível em minúsculas
    bruto: bytes = field(repr=False)

    @property
    def mensagem(self) -> str | None:
        return _texto(self.corpo.get("mensagem"))


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
                chave = _chave(resposta.status, corpo)
                return NfseEmitida(
                    chave=chave,
                    id_dps=_id_dps(resposta.status, corpo, chave),
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

    def consultar_evento(self, chave: str, tipo: str, seq: int) -> bytes | None:
        """`GET /nfse/{chave}/eventos/{tipo}/{seq}`: o XML do evento, já decodificado, ou None
        quando a NFS-e não tem esse evento (404) (T-028)."""
        if not _CHAVE.fullmatch(chave):
            raise ValueError("chave de acesso fora do formato: 50 dígitos")
        if not isinstance(tipo, str) or not _TIPO_EVENTO.fullmatch(tipo):
            raise ValueError("tipo do evento fora do formato: 6 dígitos (ex.: 101101)")
        if isinstance(seq, bool) or not isinstance(seq, int) or not 1 <= seq <= 999:
            raise ValueError("número sequencial do evento fora do formato: de 1 a 999")
        resposta = self._pedir("GET", f"nfse/{chave}/eventos/{tipo}/{seq}")
        with _anexar_corpo(resposta):
            if resposta.status == 200:
                return _evento_consultado(resposta.status, _objeto_json(resposta), tipo, seq)
            if resposta.status == 404:
                return None
            if resposta.status in (401, 422):
                raise _rejeicao(resposta)
            raise RespostaInesperada(
                resposta.status, f"HTTP {resposta.status} não previsto na consulta de eventos"
            )

    def registrar_evento(self, chave: str, pedido_assinado: bytes) -> bytes:
        """`POST /nfse/{chave}/eventos` com o pedido assinado em GZip+Base64; devolve o XML do
        evento registrado, já decodificado (T-030).

        Não repete o envio em caso de falha: quem decide é `src/cancelamento.py`.
        """
        if not isinstance(pedido_assinado, bytes):
            raise TypeError(
                f"registrar_evento espera bytes, recebido: {type(pedido_assinado).__name__}"
            )
        if not _CHAVE.fullmatch(chave):
            raise ValueError("chave de acesso fora do formato: 50 dígitos")
        if _chave_do_pedido(pedido_assinado) != chave:
            raise ValueError("o chNFSe do pedido não é a chave da rota: nada enviado")
        resposta = self._pedir(
            "POST",
            f"nfse/{chave}/eventos",
            corpo_json={"pedidoRegistroEventoXmlGZipB64": codificar(pedido_assinado)},
        )
        with _anexar_corpo(resposta):
            if resposta.status == 201:
                return _evento_xml(resposta.status, _objeto_json(resposta))
            if resposta.status in (400, 401):
                raise _rejeicao(resposta)
            raise RespostaInesperada(
                resposta.status, f"HTTP {resposta.status} não previsto no registro do evento"
            )

    def convenio(self, municipio: str) -> ConsultaParametros:
        """`GET /parametrizacao/{municipio}/convenio` no ADN (T-026)."""
        self._conferir_parametros(municipio)
        return self._parametros(f"{municipio}/convenio")

    def historico_aliquotas(self, municipio: str, codigo_servico: str) -> ConsultaParametros:
        """`GET /parametrizacao/{municipio}/{codigo}/historicoaliquotas` no ADN (T-026).

        A especificação não diz o formato de `codigoServico`. A API real recusou 6 dígitos e
        recusou 9 dígitos com zero à esquerda (DEC-041): aceita 9 dígitos ou o formato
        pontuado `NN.NN.NN.NNN`, e quem chama escolhe.
        """
        self._conferir_parametros(municipio)
        if not _CODIGO_SERVICO.fullmatch(codigo_servico):
            raise ValueError("código de serviço fora do formato: 9 dígitos ou NN.NN.NN.NNN")
        return self._parametros(f"{municipio}/{codigo_servico}/historicoaliquotas")

    def _conferir_parametros(self, municipio: str) -> None:
        if self.api != "adn":
            raise ValueError("parâmetros municipais ficam no ADN: crie o cliente com api='adn'")
        if not _MUNICIPIO.fullmatch(municipio):
            raise ValueError("código do município fora do formato: 7 dígitos (IBGE)")

    def _parametros(self, caminho: str) -> ConsultaParametros:
        resposta = self._pedir("GET", f"{_PARAMETRIZACAO}/{caminho}")
        with _anexar_corpo(resposta):
            # 400 e 404 também trazem corpo com `mensagem` (especificação do ADN).
            if resposta.status in (200, 400, 404):
                return ConsultaParametros(resposta.status, _objeto_json(resposta), resposta.corpo)
            raise RespostaInesperada(
                resposta.status, f"HTTP {resposta.status} não previsto na consulta de parâmetros"
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


def _id_dps(status: int, corpo: dict, chave: str) -> str | None:
    """O Id da DPS, se a resposta o trouxer.

    A especificação descreve `idDps` como o Id da DPS, mas a SEFIN real devolve nele o Id da
    NFS-e, "NFS" + chave (DEC-045): nesse caso não há Id da DPS, e quem confere a DPS é a
    conferência da nota (`src/nfse.py`). Qualquer outro valor é resposta inesperada.
    """
    id_dps = corpo.get("iddps")
    if isinstance(id_dps, str) and _ID_DPS.fullmatch(id_dps):
        return id_dps
    if id_dps == f"NFS{chave}":
        return None
    raise RespostaInesperada(status, "idDps ausente ou fora do formato")


def _nfse_xml(status: int, corpo: dict) -> bytes:
    texto = corpo.get("nfsexmlgzipb64")
    if not isinstance(texto, str):
        raise RespostaInesperada(status, "nfseXmlGZipB64 ausente")
    try:
        return decodificar(texto)
    except ValueError as erro:
        motivo = f"nfseXmlGZipB64 inválido: {erro}"
    raise RespostaInesperada(status, motivo)


def _chave_do_pedido(xml: bytes) -> str | None:
    """O `chNFSe` do pedido de registro de evento."""
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    try:
        raiz = etree.fromstring(xml, parser)
    except (etree.XMLSyntaxError, ValueError):
        raiz = None
    if raiz is None:
        raise ValueError("o pedido não é XML bem formado: nada enviado")
    if raiz.tag != f"{{{NS}}}pedRegEvento":
        raise ValueError(f"raiz do pedido não é pedRegEvento no namespace {NS}: nada enviado")
    return raiz.findtext(f"{{{NS}}}infPedReg/{{{NS}}}chNFSe")


def _evento_xml(status: int, corpo: dict) -> bytes:
    texto = corpo.get("eventoxmlgzipb64")
    if not isinstance(texto, str):
        raise RespostaInesperada(status, "eventoXmlGZipB64 ausente")
    try:
        return decodificar(texto)
    except ValueError as erro:
        motivo = f"eventoXmlGZipB64 inválido: {erro}"
    raise RespostaInesperada(status, motivo)


def _evento_consultado(status: int, corpo: dict, tipo: str, seq: int) -> bytes:
    """O evento da consulta `GET /nfse/{chave}/eventos/{tipo}/{seq}`.

    A especificação descreve `eventoXmlGZipB64`, mas a SEFIN real devolveu em 2026-10-13 uma
    lista `eventos`, com `tipoEvento`, `numeroPedidoRegistroEvento` e `arquivoXml` em Base64 do
    texto GZip+Base64 (Base64 em dobro) (T-030, DEC-057). As duas formas são lidas; na lista,
    vale o item do tipo e do número pedidos.
    """
    if "eventoxmlgzipb64" in corpo or "eventos" not in corpo:
        return _evento_xml(status, corpo)
    lista = corpo["eventos"]
    if not isinstance(lista, list):
        raise RespostaInesperada(status, "eventos não é uma lista")
    for item in lista:
        if not isinstance(item, dict):
            continue
        campos = {chave.lower(): valor for chave, valor in item.items() if isinstance(chave, str)}
        if str(campos.get("tipoevento")) != tipo:
            continue
        if str(campos.get("numeropedidoregistroevento")) != str(seq):
            continue
        texto = campos.get("arquivoxml")
        if not isinstance(texto, str):
            raise RespostaInesperada(status, "arquivoXml ausente no item da lista eventos")
        return _arquivo_xml(status, texto)
    raise RespostaInesperada(status, f"nenhum evento {tipo}/{seq} na lista eventos")


def _arquivo_xml(status: int, texto: str) -> bytes:
    """`arquivoXml`: GZip+Base64, ou o Base64 desse texto, como a SEFIN real devolve."""
    try:
        interno = base64.b64decode(texto, validate=True)
    except ValueError:
        interno = b""
    if interno.startswith(b"H4sI"):  # Base64 de um GZip: o Base64 veio em dobro
        texto = interno.decode("ascii")
    try:
        return decodificar(texto)
    except ValueError as erro:
        motivo = f"arquivoXml inválido: {erro}"
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
    # O envio devolve uma lista `erros`; as consultas, um objeto `erro` só; o registro de
    # evento, uma lista em `erro`, embora a especificação diga objeto (T-030, 2026-10-13).
    if "erros" in corpo:
        mensagens = _mensagens(resposta.status, corpo["erros"], "erros")
    elif isinstance(corpo.get("erro"), list):
        mensagens = _mensagens(resposta.status, corpo["erro"], "erro")
    else:
        mensagens = _mensagens(resposta.status, [corpo["erro"]] if "erro" in corpo else [], "erro")
    id_dps = corpo.get("iddps")
    return RejeicaoApi(resposta.status, id_dps if isinstance(id_dps, str) else None, mensagens)
