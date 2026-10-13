"""Eventos de NFS-e (Anexo II v1.01): o pedido de cancelamento e a conferência do evento.

O pedido de registro do evento de cancelamento (101101) é montado e validado aqui, sem rede
e sem assinatura (T-029, DEC-052); quem assina é `src/assinatura.py`.

Como em src/nfse.py, a conferência não aceita nem recusa o evento devolvido pela SEFIN: ele
já foi registrado quando chega aqui. Ela só aponta o que não bate, para quem rodou a
consulta decidir (T-028).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from lxml import etree

from src.assinatura import conferir_assinatura_do_sistema
from src.dps import NS, VERSAO, validar_xml

_N = {"n": NS}
_HOMOLOGACAO = "2"  # tpAmb da produção restrita (INV-02)

# Código do evento de cancelamento pelo emitente (Anexo II, aba TIPO EVENTOS DE NFSe).
CANCELAMENTO = "101101"
_DESCRICAO_CANCELAMENTO = "Cancelamento de NFS-e"
# cMotivo (TSCodJustCanc): 1 Erro na Emissão, 2 Serviço não Prestado, 9 Outros.
_MOTIVOS_CANCELAMENTO = (1, 2, 9)
# TSString: sem espaço nas pontas nem quebra de linha, só caracteres de U+0020 a U+00FF.
_TSSTRING = re.compile("[!-\u00ff](?:[ -\u00ff]*[!-\u00ff])?")
# Na chave de acesso, a posição 9 é o tipo de inscrição federal (2 = CNPJ) e as posições 10
# a 23 são a inscrição do emitente (Anexo I, docs/SOURCES.md).
_TIPO_INSCRICAO_CNPJ = "2"


def _digitos(valor, tamanho: int, campo: str) -> str:
    if not isinstance(valor, str) or not re.fullmatch(rf"\d{{{tamanho}}}", valor):
        raise ValueError(f"{campo} deve ter {tamanho} dígitos numéricos")
    return valor


def _texto(valor, minimo: int, maximo: int, campo: str) -> None:
    if not isinstance(valor, str) or not (minimo <= len(valor) <= maximo):
        raise ValueError(f"{campo} deve ter de {minimo} a {maximo} caracteres")
    if not _TSSTRING.fullmatch(valor):
        raise ValueError(
            f"{campo} só aceita caracteres de U+0020 a U+00FF, sem quebra de linha nem espaço "
            "nas pontas (TSString do XSD)"
        )


@dataclass(frozen=True)
class PedidoCancelamento:
    """Pedido de registro do evento de cancelamento (101101) pelo emitente da NFS-e."""

    chave: str  # chave de acesso da NFS-e, 50 dígitos
    cnpj_autor: str  # o emitente da nota (E0813)
    tp_amb: int  # 1=produção, 2=homologação; a trava de produção é da configuração (INV-02)
    dh_evento: datetime  # com fuso de hora cheia
    c_motivo: int
    x_motivo: str
    ver_aplic: str = "nfse-poc-0.1"

    def __post_init__(self):
        _digitos(self.chave, 50, "chave")
        if self.chave[8] != _TIPO_INSCRICAO_CNPJ:
            raise ValueError(
                "a chave não é de NFS-e de emitente com CNPJ (tipo de inscrição na posição 9 "
                "diferente de 2); o modelo só aceita emitente com CNPJ (DEC-024)"
            )
        _digitos(self.cnpj_autor, 14, "cnpj_autor")
        if self.cnpj_autor != self.chave[9:23]:
            raise ValueError(
                "cnpj_autor não é o CNPJ do emitente da nota (posições 10 a 23 da chave): no "
                "cancelamento, o autor do pedido é o emitente (E0813)"
            )
        if self.tp_amb not in (1, 2) or isinstance(self.tp_amb, bool):
            raise ValueError("tp_amb deve ser 1 ou 2 (E1845)")
        if not isinstance(self.dh_evento, datetime) or self.dh_evento.tzinfo is None:
            raise ValueError("dh_evento precisa de fuso horário (ex.: -03:00)")
        fuso = self.dh_evento.utcoffset()
        if fuso % timedelta(hours=1) or not (timedelta(hours=-11) <= fuso <= timedelta(hours=12)):
            raise ValueError("dh_evento precisa de fuso de hora cheia, de -11:00 a +12:00")
        if not (2000 <= self.dh_evento.year <= 2099):
            raise ValueError("dh_evento deve estar entre os anos 2000 e 2099 (TSDateTimeUTC)")
        # O XSD não aceita fração de segundo.
        object.__setattr__(self, "dh_evento", self.dh_evento.replace(microsecond=0))
        if self.c_motivo not in _MOTIVOS_CANCELAMENTO or isinstance(self.c_motivo, bool):
            raise ValueError(
                "c_motivo deve ser 1 (Erro na Emissão), 2 (Serviço não Prestado) ou 9 (Outros)"
            )
        _texto(self.x_motivo, 15, 255, "x_motivo")
        _texto(self.ver_aplic, 1, 20, "ver_aplic")

    @property
    def id(self) -> str:
        """Id do `infPedReg`: "PRE" + chave (50) + código do evento (6), 59 posições (E1827)."""
        return f"PRE{self.chave}{CANCELAMENTO}"


def _sub(pai, nome: str, texto: str | None = None):
    el = etree.SubElement(pai, f"{{{NS}}}{nome}")
    if texto is not None:
        el.text = texto
    return el


def para_xml_pedido(pedido: PedidoCancelamento) -> bytes:
    """Gera o `pedRegEvento` de cancelamento, SEM assinatura, na ordem do XSD."""
    raiz = etree.Element(f"{{{NS}}}pedRegEvento", nsmap={None: NS}, versao=VERSAO)
    inf = _sub(raiz, "infPedReg")
    inf.set("Id", pedido.id)
    _sub(inf, "tpAmb", str(pedido.tp_amb))
    _sub(inf, "verAplic", pedido.ver_aplic)
    _sub(inf, "dhEvento", pedido.dh_evento.isoformat(timespec="seconds"))
    _sub(inf, "CNPJAutor", pedido.cnpj_autor)
    _sub(inf, "chNFSe", pedido.chave)
    grupo = _sub(inf, f"e{CANCELAMENTO}")
    _sub(grupo, "xDesc", _DESCRICAO_CANCELAMENTO)
    _sub(grupo, "cMotivo", str(pedido.c_motivo))
    _sub(grupo, "xMotivo", pedido.x_motivo)
    return etree.tostring(raiz, xml_declaration=True, encoding="UTF-8")


def localizar_xsd_pedido_evento(xsd_dir: Path) -> Path | None:
    candidatos = sorted(Path(xsd_dir).glob("pedRegEvento_v*.xsd"))
    return candidatos[-1] if candidatos else None


def localizar_xsd_evento(xsd_dir: Path) -> Path | None:
    candidatos = sorted(Path(xsd_dir).glob("evento_v*.xsd"))
    return candidatos[-1] if candidatos else None


def _ler(xml: bytes) -> etree._Element | None:
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    try:
        raiz = etree.fromstring(xml, parser)
    except (etree.XMLSyntaxError, ValueError):
        return None
    return raiz if raiz.tag == f"{{{NS}}}evento" else None


def conferir_evento(
    xml: bytes, *, chave: str, tipo: str, xsd: Path, id_pedido: str | None = None
) -> list[str]:
    """Lista o que não bate no evento consultado; vazia quando está tudo certo.

    `tipo` é o código do evento pedido, 6 dígitos (ex.: "101101", cancelamento): o grupo
    específico do pedido de registro se chama `e<tipo>`. Com `id_pedido`, confere também se o
    pedido dentro do evento é o que foi enviado (T-030).
    """
    raiz = _ler(xml)
    if raiz is None:
        return ["o retorno não é um evento em XML"]

    problemas = []
    erros = validar_xml(xml, xsd)
    if erros:
        extra = f" (e mais {len(erros) - 1})" if len(erros) > 1 else ""
        problemas.append(f"inválido contra {xsd.name}: {erros[0]}{extra}")

    pedido = raiz.find("n:infEvento/n:pedRegEvento/n:infPedReg", _N)
    if pedido is None or pedido.findtext("n:chNFSe", namespaces=_N) != chave:
        problemas.append("o evento não é da NFS-e consultada (chNFSe diferente)")
    if pedido is None or pedido.find(f"n:e{tipo}", _N) is None:
        problemas.append(f"o evento não é do tipo pedido ({tipo})")
    elif pedido.findtext("n:tpAmb", namespaces=_N) != _HOMOLOGACAO:
        problemas.append("tpAmb do evento não é 2 (produção restrita)")
    if id_pedido is not None and pedido is not None and pedido.get("Id") != id_pedido:
        problemas.append("o evento não é do pedido enviado (Id do pedido diferente)")

    try:
        conferir_assinatura_do_sistema(xml)
    except ValueError:
        problemas.append("assinatura do evento não confere com o certificado que ele traz")
    return problemas
