"""Modelo da DPS e geração do XML (sem assinatura) + validação offline contra o XSD.

ATENÇÃO: a estrutura abaixo segue o layout da DPS v1.x como eu o conheço, mas o XSD
oficial é a fonte de verdade. Rode `scripts/gerar_dps.py`: se a validação reclamar
de ordem/obrigatoriedade de elementos, ajuste `para_xml()` conforme o XSD.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from lxml import etree

NS = "http://www.sped.fazenda.gov.br/nfse"
VERSAO = "1.01"  # confira a versão vigente na documentação oficial


def _so_digitos(valor: str, tamanho: int, campo: str) -> str:
    if not re.fullmatch(rf"\d{{{tamanho}}}", valor or ""):
        raise ValueError(f"{campo} deve ter {tamanho} dígitos numéricos, recebido: {valor!r}")
    return valor


def _dinheiro(valor: Decimal) -> str:
    return f"{Decimal(valor):.2f}"


# ----------------------------------------------------------------- modelo

@dataclass(frozen=True)
class Prestador:
    cnpj: str
    inscricao_municipal: str | None
    op_simp_nac: int          # 1=Não optante, 2=MEI, 3=ME/EPP (conferir tabela no manual)
    reg_esp_trib: int = 0     # 0=Nenhum (conferir tabela no manual)

    def __post_init__(self):
        _so_digitos(self.cnpj, 14, "prestador.cnpj")


@dataclass(frozen=True)
class Tomador:
    nome: str
    cnpj: str | None = None
    cpf: str | None = None

    def __post_init__(self):
        if bool(self.cnpj) == bool(self.cpf):
            raise ValueError("tomador: informe CNPJ ou CPF (apenas um)")
        if self.cnpj:
            _so_digitos(self.cnpj, 14, "tomador.cnpj")
        if self.cpf:
            _so_digitos(self.cpf, 11, "tomador.cpf")


@dataclass(frozen=True)
class Servico:
    c_loc_prestacao: str      # código IBGE do município (7 dígitos)
    c_trib_nac: str           # código de tributação nacional (6 dígitos)
    descricao: str

    def __post_init__(self):
        _so_digitos(self.c_loc_prestacao, 7, "servico.c_loc_prestacao")
        _so_digitos(self.c_trib_nac, 6, "servico.c_trib_nac")
        if not self.descricao.strip():
            raise ValueError("servico.descricao é obrigatória")


@dataclass(frozen=True)
class Valores:
    v_serv: Decimal
    trib_issqn: int = 1       # 1=Operação tributável (conferir tabela)
    tp_ret_issqn: int = 1     # 1=Sem retenção (conferir tabela)
    p_aliq: Decimal | None = None  # só se o município/regime exigir

    def __post_init__(self):
        if Decimal(self.v_serv) <= 0:
            raise ValueError("valores.v_serv deve ser > 0")


@dataclass(frozen=True)
class Dps:
    tp_amb: int               # 1=produção, 2=homologação
    c_loc_emi: str            # IBGE do município emissor (7 dígitos)
    serie: int
    n_dps: int
    d_compet: date
    dh_emi: datetime          # com fuso horário (tzinfo obrigatório)
    prestador: Prestador
    tomador: Tomador
    servico: Servico
    valores: Valores
    ver_aplic: str = "nfse-poc-0.1"
    tp_emit: int = 1          # 1=Prestador

    def __post_init__(self):
        if self.tp_amb not in (1, 2):
            raise ValueError("tp_amb deve ser 1 ou 2")
        _so_digitos(self.c_loc_emi, 7, "c_loc_emi")
        if self.dh_emi.tzinfo is None:
            raise ValueError("dh_emi precisa de fuso horário (ex.: -03:00)")
        if not (0 < self.serie <= 99999):
            raise ValueError("serie deve estar entre 1 e 99999")
        if not (0 < self.n_dps <= 999_999_999_999_999):
            raise ValueError("n_dps deve ter até 15 dígitos")

    @property
    def id(self) -> str:
        return gerar_id(self.c_loc_emi, self.prestador.cnpj, self.serie, self.n_dps)


def gerar_id(c_loc_emi: str, cnpj: str, serie: int, n_dps: int) -> str:
    """Id da infDPS: 'DPS' + cLocEmi(7) + tipoInscrição(1; 2=CNPJ) + CNPJ(14) + série(5) + nDPS(15) = 45."""
    id_ = f"DPS{c_loc_emi}2{cnpj}{serie:05d}{n_dps:015d}"
    assert len(id_) == 45, id_
    return id_


# -------------------------------------------------------------------- XML

def _sub(pai, nome: str, texto: str | None = None):
    el = etree.SubElement(pai, f"{{{NS}}}{nome}")
    if texto is not None:
        el.text = texto
    return el


def para_xml(dps: Dps) -> bytes:
    """Gera o XML da DPS, SEM assinatura. Ordem dos elementos = ordem do XSD."""
    raiz = etree.Element(f"{{{NS}}}DPS", nsmap={None: NS}, versao=VERSAO)
    inf = _sub(raiz, "infDPS")
    inf.set("Id", dps.id)

    _sub(inf, "tpAmb", str(dps.tp_amb))
    _sub(inf, "dhEmi", dps.dh_emi.isoformat(timespec="seconds"))
    _sub(inf, "verAplic", dps.ver_aplic)
    _sub(inf, "serie", str(dps.serie))
    _sub(inf, "nDPS", str(dps.n_dps))
    _sub(inf, "dCompet", dps.d_compet.isoformat())
    _sub(inf, "tpEmit", str(dps.tp_emit))
    _sub(inf, "cLocEmi", dps.c_loc_emi)

    prest = _sub(inf, "prest")
    _sub(prest, "CNPJ", dps.prestador.cnpj)
    if dps.prestador.inscricao_municipal:
        _sub(prest, "IM", dps.prestador.inscricao_municipal)
    reg = _sub(prest, "regTrib")
    _sub(reg, "opSimpNac", str(dps.prestador.op_simp_nac))
    _sub(reg, "regEspTrib", str(dps.prestador.reg_esp_trib))

    toma = _sub(inf, "toma")
    if dps.tomador.cnpj:
        _sub(toma, "CNPJ", dps.tomador.cnpj)
    else:
        _sub(toma, "CPF", dps.tomador.cpf)
    _sub(toma, "xNome", dps.tomador.nome)

    serv = _sub(inf, "serv")
    loc = _sub(serv, "locPrest")
    _sub(loc, "cLocPrestacao", dps.servico.c_loc_prestacao)
    cserv = _sub(serv, "cServ")
    _sub(cserv, "cTribNac", dps.servico.c_trib_nac)
    _sub(cserv, "xDescServ", dps.servico.descricao)

    val = _sub(inf, "valores")
    vsp = _sub(val, "vServPrest")
    _sub(vsp, "vServ", _dinheiro(dps.valores.v_serv))
    trib = _sub(val, "trib")
    tm = _sub(trib, "tribMun")
    _sub(tm, "tribISSQN", str(dps.valores.trib_issqn))
    _sub(tm, "tpRetISSQN", str(dps.valores.tp_ret_issqn))
    if dps.valores.p_aliq is not None:
        _sub(tm, "pAliq", _dinheiro(dps.valores.p_aliq))
    tot = _sub(trib, "totTrib")
    _sub(tot, "indTotTrib", "0")

    return etree.tostring(raiz, xml_declaration=True, encoding="UTF-8")


# -------------------------------------------------------------- validação

def localizar_xsd_dps(xsd_dir: Path) -> Path | None:
    candidatos = sorted(Path(xsd_dir).glob("DPS_v*.xsd"))
    return candidatos[-1] if candidatos else None


def validar_xml(xml: bytes, xsd_path: Path) -> list[str]:
    """Valida contra o XSD oficial. Retorna lista de erros (vazia = válido)."""
    schema = etree.XMLSchema(etree.parse(str(xsd_path)))
    doc = etree.fromstring(xml)
    if schema.validate(doc):
        return []
    return [f"linha {e.line}: {e.message}" for e in schema.error_log]
