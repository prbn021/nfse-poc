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


# Simples Nacional (docs/SPEC.md §6, Anexo I v1.01).
NAO_OPTANTE, MEI, ME_EPP = 1, 2, 3
_OP_SIMP_NAC = {NAO_OPTANTE: "Não Optante", MEI: "MEI", ME_EPP: "ME/EPP"}
# regApTribSN: 1 = federais e municipal pelo SN; 2 e 3 = ISSQN por fora (T-023).
APURACAO_PELO_SN = 1
_REG_AP_TRIB_SN = (1, 2, 3)
# Série da DPS de aplicativo próprio (Anexo I v1.01, E0010; DEC-019).
SERIE_MIN, SERIE_MAX = 1, 49999

# Campos opcionais das notas atuais (T-018, DEC-023).
_FONE = re.compile(r"[0-9]{6,20}")  # TSTelefone
_EMAIL_MAX = 80  # TSEmail
# E0148: "estrutura de e-mail". Conferência simples: algo@dominio.tld, sem espaços.
_EMAIL = re.compile(r"[^@\s]+@[^@\s.]+(\.[^@\s.]+)+")
_C_TRIB_MUN = re.compile(r"[0-9]{3}")  # TCCodTribMun
# CST do PIS/COFINS (TSTipoCST).
_CST = frozenset(
    [f"{n:02d}" for n in range(10)]
    + ["49", *(str(n) for n in range(50, 57)), *(str(n) for n in range(60, 68))]
    + [*(str(n) for n in range(70, 76)), "98", "99"]
)
# tpRetPisCofins (TSTipoRetPISCofins): fora de 0 e 2, o Anexo I exige vRetCSLL, que fica
# para a T-025 (DEC-033).
_TP_RET_PIS_COFINS = range(10)
_TP_RET_PIS_COFINS_SEM_CSLL = (0, 2)


def fone_valido(fone: object) -> bool:
    return isinstance(fone, str) and _FONE.fullmatch(fone) is not None


def email_valido(email: object) -> bool:
    return (
        isinstance(email, str) and len(email) <= _EMAIL_MAX and _EMAIL.fullmatch(email) is not None
    )


# ----------------------------------------------------------------- modelo


@dataclass(frozen=True)
class Prestador:
    """Tudo aqui é do emitente: nenhum campo tem default (INV-06)."""

    cnpj: str
    inscricao_municipal: str | None
    fone: str | None  # só dígitos, 6 a 20
    email: str | None
    op_simp_nac: int  # 1=Não Optante, 2=MEI, 3=ME/EPP
    reg_esp_trib: int  # 0=Nenhum
    reg_ap_trib_sn: int | None  # só ME/EPP: 1=pelo SN, 2 e 3=ISSQN por fora

    def __post_init__(self):
        _so_digitos(self.cnpj, 14, "prestador.cnpj")
        if self.fone is not None and not fone_valido(self.fone):
            raise ValueError("prestador.fone deve ter de 6 a 20 dígitos, sem espaços nem sinais")
        if self.email is not None and not email_valido(self.email):
            raise ValueError(
                f"prestador.email sem estrutura de e-mail (nome@dominio) ou com mais de "
                f"{_EMAIL_MAX} caracteres (E0148)"
            )
        if self.op_simp_nac not in _OP_SIMP_NAC:
            raise ValueError(
                f"prestador.op_simp_nac deve ser 1, 2 ou 3, recebido: {self.op_simp_nac!r}"
            )
        if self.op_simp_nac != ME_EPP:
            if self.reg_ap_trib_sn is not None:
                raise ValueError("regApTribSN só existe para ME/EPP (op_simp_nac = 3)")
            raise ValueError(
                f"emitente {_OP_SIMP_NAC[self.op_simp_nac]} ainda não suportado: "
                "o modelo só emite para ME/EPP (DEC-022)"
            )
        if self.reg_ap_trib_sn is None:
            raise ValueError("regApTribSN é obrigatório para ME/EPP (prestador.reg_ap_trib_sn)")
        if self.reg_ap_trib_sn not in _REG_AP_TRIB_SN:
            raise ValueError(
                f"prestador.reg_ap_trib_sn deve ser 1, 2 ou 3, recebido: {self.reg_ap_trib_sn!r}"
            )
        if self.reg_ap_trib_sn != APURACAO_PELO_SN:
            raise ValueError(
                f"regApTribSN = {self.reg_ap_trib_sn} (ISSQN por fora do Simples) ainda não "
                "suportado (T-023)"
            )
        # Anexo I: ME/EPP com apuração pelo SN não tem regime especial.
        if self.reg_esp_trib != 0:
            raise ValueError(
                "regEspTrib deve ser 0 (Nenhum) para ME/EPP com apuração pelo Simples Nacional"
            )


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
    c_loc_prestacao: str  # código IBGE do município (7 dígitos)
    c_trib_nac: str  # código de tributação nacional (6 dígitos)
    descricao: str
    # Código de tributação do município (3 dígitos). Precisa existir no município de
    # incidência (E0314), o que só o servidor confere.
    c_trib_mun: str | None = None

    def __post_init__(self):
        _so_digitos(self.c_loc_prestacao, 7, "servico.c_loc_prestacao")
        _so_digitos(self.c_trib_nac, 6, "servico.c_trib_nac")
        if self.c_trib_mun is not None and not _C_TRIB_MUN.fullmatch(self.c_trib_mun):
            raise ValueError("servico.c_trib_mun deve ter 3 dígitos numéricos")
        if not self.descricao.strip():
            raise ValueError("servico.descricao é obrigatória")


@dataclass(frozen=True)
class PisCofins:
    """Grupo tribFed/piscofins, só com CST e tipo de retenção (T-018, DEC-023).

    Base de cálculo, alíquotas e valores de PIS/COFINS ficam de fora.
    """

    cst: str  # dois dígitos, da tabela TSTipoCST (ex.: "08" = sem incidência)
    tp_ret_pis_cofins: int | None = None  # 0 ou 2; os demais exigem vRetCSLL (T-025)

    def __post_init__(self):
        if self.cst not in _CST:
            raise ValueError(f"CST do PIS/COFINS fora da tabela: {self.cst!r}")
        tipo = self.tp_ret_pis_cofins
        if tipo is None:
            return
        if isinstance(tipo, bool) or not isinstance(tipo, int) or tipo not in _TP_RET_PIS_COFINS:
            raise ValueError(f"tpRetPisCofins fora da tabela (0 a 9): {tipo!r}")
        if tipo not in _TP_RET_PIS_COFINS_SEM_CSLL:
            raise ValueError(
                f"tpRetPisCofins = {tipo} ainda não suportado: exige vRetCSLL (T-025, DEC-033)"
            )


@dataclass(frozen=True)
class Valores:
    v_serv: Decimal
    # % aproximado dos tributos pela alíquota do Simples; muda por emitente e competência
    # (Q-18), por isso é dado da nota, sem default.
    p_tot_trib_sn: Decimal
    trib_issqn: int = 1  # 1=Operação tributável
    tp_ret_issqn: int = 1  # 1=Não Retido, 2=Retido pelo Tomador, 3=Retido pelo Intermediário
    p_aliq: Decimal | None = None  # ME/EPP pelo SN: só com retenção, e então obrigatório
    pis_cofins: PisCofins | None = None  # grupo tribFed/piscofins (T-018)

    def __post_init__(self):
        if Decimal(self.v_serv) <= 0:
            raise ValueError("valores.v_serv deve ser > 0")
        # TSDec2V2: de 0 a 99.99, com até 2 casas. Decimal, para não arredondar sem aviso.
        p = self.p_tot_trib_sn
        if (
            not isinstance(p, Decimal)
            or not p.is_finite()
            or not (0 <= p < 100)
            or p.as_tuple().exponent < -2
        ):
            raise ValueError(
                "valores.p_tot_trib_sn deve ser um Decimal de 0 a 99.99, com até 2 casas, "
                f"recebido: {p!r}"
            )


@dataclass(frozen=True)
class Dps:
    tp_amb: int  # 1=produção, 2=homologação
    c_loc_emi: str  # IBGE do município emissor (7 dígitos)
    serie: int
    n_dps: int
    d_compet: date
    dh_emi: datetime  # com fuso horário (tzinfo obrigatório)
    prestador: Prestador
    tomador: Tomador
    servico: Servico
    valores: Valores
    ver_aplic: str = "nfse-poc-0.1"
    tp_emit: int = 1  # 1=Prestador

    def __post_init__(self):
        if self.tp_amb not in (1, 2):
            raise ValueError("tp_amb deve ser 1 ou 2")
        _so_digitos(self.c_loc_emi, 7, "c_loc_emi")
        if self.dh_emi.tzinfo is None:
            raise ValueError("dh_emi precisa de fuso horário (ex.: -03:00)")
        if not (SERIE_MIN <= self.serie <= SERIE_MAX):
            raise ValueError(
                f"serie deve estar entre {SERIE_MIN} e {SERIE_MAX}, a faixa do aplicativo próprio; "
                f"as de 50000 a 89999 são dos emissores oficiais (E0010), recebido: {self.serie!r}"
            )
        if not (0 < self.n_dps <= 999_999_999_999_999):
            raise ValueError("n_dps deve ter até 15 dígitos")
        # Anexo I, ME/EPP com ISSQN pelo SN (o único caso aceito por Prestador), sem
        # benefício municipal: pAliq só com retenção do ISSQN, e então é obrigatório.
        retido = self.valores.tp_ret_issqn in (2, 3)
        if retido and self.valores.p_aliq is None:
            raise ValueError("pAliq é obrigatório quando o ISSQN é retido (tp_ret_issqn 2 ou 3)")
        if not retido and self.valores.p_aliq is not None:
            raise ValueError("pAliq não pode ser informado sem retenção do ISSQN (tp_ret_issqn 1)")

    @property
    def id(self) -> str:
        return gerar_id(self.c_loc_emi, self.prestador.cnpj, self.serie, self.n_dps)


def gerar_id(c_loc_emi: str, cnpj: str, serie: int, n_dps: int) -> str:
    """Id da infDPS, 45 posições (INV-04).

    'DPS' + cLocEmi(7) + tipoInscrição(1; 2=CNPJ) + CNPJ(14) + série(5) + nDPS(15).
    """
    id_ = f"DPS{c_loc_emi}2{cnpj}{serie:05d}{n_dps:015d}"
    assert len(id_) == 45, id_  # noqa: S101 (rede de segurança de INV-04)
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
    if dps.prestador.fone is not None:
        _sub(prest, "fone", dps.prestador.fone)
    if dps.prestador.email is not None:
        _sub(prest, "email", dps.prestador.email)
    reg = _sub(prest, "regTrib")
    _sub(reg, "opSimpNac", str(dps.prestador.op_simp_nac))
    if dps.prestador.reg_ap_trib_sn is not None:
        _sub(reg, "regApTribSN", str(dps.prestador.reg_ap_trib_sn))
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
    if dps.servico.c_trib_mun is not None:
        _sub(cserv, "cTribMun", dps.servico.c_trib_mun)
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
    if dps.valores.pis_cofins is not None:
        pc = _sub(_sub(trib, "tribFed"), "piscofins")
        _sub(pc, "CST", dps.valores.pis_cofins.cst)
        if dps.valores.pis_cofins.tp_ret_pis_cofins is not None:
            _sub(pc, "tpRetPisCofins", str(dps.valores.pis_cofins.tp_ret_pis_cofins))
    # ME/EPP: indTotTrib é proibido (E0712); vai o percentual do Simples (DEC-013).
    tot = _sub(trib, "totTrib")
    _sub(tot, "pTotTribSN", _dinheiro(dps.valores.p_tot_trib_sn))

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
