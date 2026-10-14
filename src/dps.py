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


# TSString: sem espaço nas pontas nem quebra de linha, só caracteres de U+0020 a U+00FF.
TSSTRING = re.compile("[!-\u00ff](?:[ -\u00ff]*[!-\u00ff])?")


def texto_tsstring(valor: object, minimo: int, maximo: int, campo: str) -> None:
    """Texto do tipo TSString do XSD, de `minimo` a `maximo` caracteres."""
    if not isinstance(valor, str) or not (minimo <= len(valor) <= maximo):
        raise ValueError(f"{campo} deve ter de {minimo} a {maximo} caracteres")
    if not TSSTRING.fullmatch(valor):
        raise ValueError(
            f"{campo} só aceita caracteres de U+0020 a U+00FF, sem quebra de linha nem espaço "
            "nas pontas (TSString do XSD)"
        )


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

# Grupo de obra (T-020, DEC-047). Anexo I v1.01, E0370: estes subitens exigem o grupo;
# E0372: os demais o proíbem, exceto o 99.01.01.
CODIGOS_DE_OBRA = frozenset([
    "070201", "070202", "070401", "070501", "070502", "070601", "070602",
    "070701", "070801", "071701", "071901", "141403", "141404",
])  # fmt: skip
_OBRA_PERMITIDA = "990101"
_CEP = re.compile(r"[0-9]{8}")  # TSCEP
_C_CIB = 8  # TSCodCIB: 7 caracteres + DV (E0373, conferido só pelo servidor)
_C_OBRA_MAX = 30  # TSCodObra
_INSC_IMOB_FISC_MAX = 30  # TSInscImobFisc

# Grupo IBS/CBS (T-034, DEC-069). Anexo VI v1.04.01 (NT 009), regras 690 e 692: o grupo só
# é permitido a partir da competência 01/01/2026 (E0850) e é obrigatório a partir de
# 01/10/2026 (E0855), também para ME/EPP (a produção restrita recusa; DEC-060, DEC-069).
IBSCBS_PERMITIDO_DESDE = date(2026, 1, 1)
IBSCBS_OBRIGATORIO_DESDE = date(2026, 10, 1)
# cIndOp com indNFSe = "S" no Anexo VII v1.03.00 (NT 009), em gov-docs/; os demais são de
# NF-e, de NFS-e Via ou sem documento, e a SEFIN os recusa (E0901).
C_IND_OP_NFSE = frozenset([
    "010101", "010102", "010103", "010106", "020101", "020102", "020201", "020202",
    "020301", "020401", "030101", "030102", "040101", "050101", "050102", "050201",
    "060101", "070101", "070102", "100101", "100102", "100201", "100301", "100302",
    "100401", "100501", "100502", "100601",
])  # fmt: skip
# Anexo VI, E0932 e E0928: estes cIndOp exigem o grupo imovel, que o modelo ainda não
# tem, exceto nos subitens de obra abaixo (a lista da regra, sem os 14.14).
C_IND_OP_IMOVEL = frozenset(["020101", "020201", "020202", "020301", "020401"])
CODIGOS_DE_OBRA_SEM_IMOVEL = CODIGOS_DE_OBRA - {"141403", "141404"}
_C_TRIB_NAC_IMOVEL = "9903"  # 99.03: cIndOp obrigatoriamente 02XXXX (E0902)
_C_IND_OP = re.compile(r"[0-9]{6}")  # TSRTCCodIndOp
_C_CLASS_TRIB = re.compile(r"[0-9]{6}")  # TSRTCCodClassTrib
_C_NBS = re.compile(r"[0-9]{9}")  # TSCodNBS
# Anexo VI, regra 448: no subitem 99.03, o NBS é 1.1002.10.00 ou 1.1002.20.00.
_NBS_99_03 = ("110021000", "110022000")


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


def _texto(valor: object, maximo: int, campo: str) -> None:
    """TSString: de 1 a `maximo` caracteres, sem espaço no início nem no fim."""
    if not isinstance(valor, str) or not valor.strip() or valor != valor.strip():
        raise ValueError(f"{campo} deve ser preenchido, sem espaço no início nem no fim")
    if len(valor) > maximo:
        raise ValueError(f"{campo} deve ter no máximo {maximo} caracteres")


def _identificador(valor: object, maximo: int, campo: str) -> None:
    """Código livre (xs:string) de 1 a `maximo` caracteres, que não seja só espaços."""
    if not isinstance(valor, str) or not valor.strip() or len(valor) > maximo:
        raise ValueError(f"{campo} deve ter de 1 a {maximo} caracteres")


@dataclass(frozen=True)
class EnderecoObra:
    """Endereço nacional da obra (TCEnderObraEvento). O servidor confere se o CEP é do
    município do local da prestação (E0380); o modelo não tem tabela de CEPs."""

    cep: str | None
    logradouro: str
    numero: str
    bairro: str
    complemento: str | None = None

    def __post_init__(self):
        if self.cep is None:
            raise ValueError(
                "endereço da obra no exterior (endExt, sem CEP) ainda não suportado (T-022)"
            )
        if not isinstance(self.cep, str) or not _CEP.fullmatch(self.cep):
            raise ValueError("obra.endereco.cep deve ter 8 dígitos numéricos")
        _texto(self.logradouro, 255, "obra.endereco.logradouro")
        _texto(self.numero, 60, "obra.endereco.numero")
        _texto(self.bairro, 60, "obra.endereco.bairro")
        if self.complemento is not None:
            _texto(self.complemento, 156, "obra.endereco.complemento")


@dataclass(frozen=True)
class Obra:
    """Grupo serv/obra (TCInfoObra): exatamente uma identificação, entre o número da obra
    (CNO ou CEI), o CIB e o endereço."""

    c_obra: str | None = None
    c_cib: str | None = None
    endereco: EnderecoObra | None = None
    insc_imob_fisc: str | None = None

    def __post_init__(self):
        informados = [c for c in (self.c_obra, self.c_cib, self.endereco) if c is not None]
        if len(informados) != 1:
            raise ValueError(
                "obra: informe exatamente uma identificação: c_obra (CNO ou CEI), c_cib ou endereco"
            )
        if self.c_obra is not None:
            _identificador(self.c_obra, _C_OBRA_MAX, "obra.c_obra")
        if self.c_cib is not None and (
            not isinstance(self.c_cib, str) or len(self.c_cib) != _C_CIB
        ):
            raise ValueError(f"obra.c_cib deve ter {_C_CIB} caracteres")
        if self.insc_imob_fisc is not None:
            _identificador(self.insc_imob_fisc, _INSC_IMOB_FISC_MAX, "obra.insc_imob_fisc")


@dataclass(frozen=True)
class Servico:
    c_loc_prestacao: str  # código IBGE do município (7 dígitos)
    c_trib_nac: str  # código de tributação nacional (6 dígitos)
    descricao: str
    # Código de tributação do município (3 dígitos). Precisa existir no município de
    # incidência (E0314), o que só o servidor confere.
    c_trib_mun: str | None = None
    obra: Obra | None = None  # obrigatório para CODIGOS_DE_OBRA (T-020)
    # Código NBS do serviço, 9 dígitos sem pontos (Anexo B; o do serviço está no Anexo VIII).
    # Obrigatório com o grupo IBS/CBS (E0322, DEC-070); a existência (E0316) fica com o servidor.
    c_nbs: str | None = None

    def __post_init__(self):
        _so_digitos(self.c_loc_prestacao, 7, "servico.c_loc_prestacao")
        _so_digitos(self.c_trib_nac, 6, "servico.c_trib_nac")
        if self.c_trib_mun is not None and not _C_TRIB_MUN.fullmatch(self.c_trib_mun):
            raise ValueError("servico.c_trib_mun deve ter 3 dígitos numéricos")
        if not self.descricao.strip():
            raise ValueError("servico.descricao é obrigatória")
        if self.c_nbs is not None and (
            not isinstance(self.c_nbs, str) or not _C_NBS.fullmatch(self.c_nbs)
        ):
            raise ValueError(
                f"servico.c_nbs deve ter 9 dígitos, sem pontos, recebido: {self.c_nbs!r}"
            )
        if self.c_trib_nac in CODIGOS_DE_OBRA and self.obra is None:
            raise ValueError(
                f"o código de tributação nacional {self.c_trib_nac} é de obra: o grupo de obra "
                "é obrigatório (servico.obra; E0370)"
            )
        if (
            self.obra is not None
            and self.c_trib_nac not in CODIGOS_DE_OBRA
            and self.c_trib_nac != _OBRA_PERMITIDA
        ):
            raise ValueError(
                f"o código de tributação nacional {self.c_trib_nac} não é de obra: o grupo de "
                "obra não é permitido (E0372)"
            )


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
class IbsCbs:
    """Grupo IBSCBS mínimo da DPS (TCRTCInfoIBSCBS; T-034, DEC-069).

    Só o enquadramento da operação: os valores de IBS e CBS são calculados pela SEFIN.
    `finNFSe` sai sempre 0 (NFS-e regular, único valor do XSD) e `indDest` sempre 0 (o
    destinatário é o tomador; o grupo dest ainda não é suportado). Os códigos variam pelo
    serviço e pela operação (Anexo VIII), por isso são dados da nota, sem default.
    """

    c_ind_op: str  # código indicador da operação (Anexo VII)
    c_class_trib: str  # classificação tributária; os 3 primeiros dígitos são o CST (E0959)
    ind_final: int | None = None  # 1 = uso ou consumo pessoal (art. 57)

    def __post_init__(self):
        if not isinstance(self.c_ind_op, str) or not _C_IND_OP.fullmatch(self.c_ind_op):
            raise ValueError(f"ibs_cbs.c_ind_op deve ter 6 dígitos, recebido: {self.c_ind_op!r}")
        if self.c_ind_op not in C_IND_OP_NFSE:
            raise ValueError(
                f"cIndOp {self.c_ind_op} não é aceito na NFS-e: use um código do Anexo VII "
                "marcado para NFS-e (E0901)"
            )
        if not isinstance(self.c_class_trib, str) or not _C_CLASS_TRIB.fullmatch(self.c_class_trib):
            raise ValueError(
                f"ibs_cbs.c_class_trib deve ter 6 dígitos, recebido: {self.c_class_trib!r}"
            )
        valor = self.ind_final
        if valor is not None and (
            isinstance(valor, bool) or not isinstance(valor, int) or valor not in (0, 1)
        ):
            raise ValueError(f"ibs_cbs.ind_final deve ser 0 ou 1, recebido: {valor!r}")

    @property
    def cst(self) -> str:
        """CST do IBS e da CBS: os 3 primeiros dígitos do cClassTrib (E0959)."""
        return self.c_class_trib[:3]


# Substituição (T-031). Anexo I v1.01, grupo infDPS/subst: o XSD (TSCodJustSubst) pede o
# código com dois dígitos, embora o Anexo I diga tamanho 1 (docs/SOURCES.md).
OUTROS = 99
MOTIVOS_SUBSTITUICAO = (1, 2, 3, 4, 5, OUTROS)


@dataclass(frozen=True)
class Substituicao:
    """Grupo subst: a NFS-e que esta DPS substitui (TCSubstituicao)."""

    chave: str  # chave de acesso da NFS-e substituída, 50 dígitos
    # 1 Desenquadramento do Simples Nacional, 2 Enquadramento no Simples Nacional,
    # 3 Inclusão retroativa de imunidade/isenção, 4 Exclusão retroativa de imunidade/isenção,
    # 5 Rejeição pelo tomador ou intermediário responsável, 99 Outros.
    c_motivo: int
    x_motivo: str | None = None  # obrigatório com 99 (E0078)

    def __post_init__(self):
        if not isinstance(self.chave, str) or not re.fullmatch(r"\d{50}", self.chave):
            raise ValueError("subst.chave deve ter 50 dígitos numéricos")
        if (
            isinstance(self.c_motivo, bool)
            or not isinstance(self.c_motivo, int)
            or self.c_motivo not in MOTIVOS_SUBSTITUICAO
        ):
            raise ValueError(
                "subst.c_motivo deve ser 1, 2, 3, 4, 5 ou 99 (TSCodJustSubst), "
                f"recebido: {self.c_motivo!r}"
            )
        if self.x_motivo is None:
            if self.c_motivo == OUTROS:
                raise ValueError("subst.x_motivo é obrigatório com o motivo 99, Outros (E0078)")
        else:
            texto_tsstring(self.x_motivo, 15, 255, "subst.x_motivo")


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
    subst: Substituicao | None = None  # NFS-e substituída (T-031)
    ibs_cbs: IbsCbs | None = None  # obrigatório desde a competência 01/10/2026 (T-034)

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
        if self.subst is not None:
            self._conferir_chave_substituida(self.subst.chave)
        self._conferir_ibs_cbs()

    def _conferir_ibs_cbs(self) -> None:
        # Anexo VI v1.04.01: regras 690 (E0850), 692 (E0855), 447 (E0322), 697 (E0902),
        # 448 (NBS do 99.03), 719 (E0932).
        if self.ibs_cbs is None:
            if self.d_compet >= IBSCBS_OBRIGATORIO_DESDE:
                raise ValueError(
                    "o grupo IBS/CBS (ibs_cbs) é obrigatório com competência a partir de "
                    "01/10/2026 (E0855)"
                )
            return
        if self.d_compet < IBSCBS_PERMITIDO_DESDE:
            raise ValueError(
                "o grupo IBS/CBS (ibs_cbs) só é permitido com competência a partir de "
                "01/01/2026 (E0850)"
            )
        if self.servico.c_nbs is None:
            raise ValueError(
                "o código NBS do serviço (servico.c_nbs) é obrigatório com o grupo IBS/CBS (E0322)"
            )
        c_ind_op, c_trib_nac = self.ibs_cbs.c_ind_op, self.servico.c_trib_nac
        if c_trib_nac.startswith(_C_TRIB_NAC_IMOVEL) and not c_ind_op.startswith("02"):
            raise ValueError(
                f"o código de tributação nacional {c_trib_nac} (99.03) exige cIndOp 02XXXX (E0902)"
            )
        if c_trib_nac.startswith(_C_TRIB_NAC_IMOVEL) and self.servico.c_nbs not in _NBS_99_03:
            raise ValueError(
                f"o código de tributação nacional {c_trib_nac} (99.03) exige o NBS 1.1002.10.00 "
                "ou 1.1002.20.00 (Anexo VI, regra 448)"
            )
        if c_ind_op in C_IND_OP_IMOVEL and c_trib_nac not in CODIGOS_DE_OBRA_SEM_IMOVEL:
            raise ValueError(
                f"cIndOp {c_ind_op} é de operação com imóvel e exige o grupo imovel (E0932), "
                "ainda não suportado; nos subitens de obra o grupo não é exigido"
            )

    def _conferir_chave_substituida(self, chave: str) -> None:
        # E0042: município (posições 1 a 7), tipo de inscrição (9) e inscrição (10 a 23) da
        # chave substituída batem com o Id desta DPS (Anexo I). O DV fica com o servidor: o
        # algoritmo não está documentado.
        for parte, esperado, nome in (
            (chave[0:7], self.c_loc_emi, "município"),
            (chave[8], "2", "tipo de inscrição"),
            (chave[9:23], self.prestador.cnpj, "CNPJ"),
        ):
            if parte != esperado:
                raise ValueError(
                    f"a chave substituída é de outro {nome}: ela precisa ter o mesmo município, "
                    "tipo de inscrição e CNPJ do Id desta DPS (E0042)"
                )

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
    if dps.subst is not None:
        subst = _sub(inf, "subst")
        _sub(subst, "chSubstda", dps.subst.chave)
        _sub(subst, "cMotivo", f"{dps.subst.c_motivo:02d}")
        if dps.subst.x_motivo is not None:
            _sub(subst, "xMotivo", dps.subst.x_motivo)

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
    if dps.servico.c_nbs is not None:
        _sub(cserv, "cNBS", dps.servico.c_nbs)
    if dps.servico.obra is not None:
        _obra_xml(serv, dps.servico.obra)

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
    if dps.ibs_cbs is not None:
        _ibs_cbs_xml(inf, dps.ibs_cbs)

    return etree.tostring(raiz, xml_declaration=True, encoding="UTF-8")


def _ibs_cbs_xml(inf, grupo: IbsCbs) -> None:
    # Ordem de TCRTCInfoIBSCBS: finNFSe, indFinal, cIndOp, (tpOper, gRefNFSe, tpEnteGov),
    # indDest, (dest, imovel), valores/trib/gIBSCBS (CST, cClassTrib).
    el = _sub(inf, "IBSCBS")
    _sub(el, "finNFSe", "0")
    if grupo.ind_final is not None:
        _sub(el, "indFinal", str(grupo.ind_final))
    _sub(el, "cIndOp", grupo.c_ind_op)
    _sub(el, "indDest", "0")
    g = _sub(_sub(_sub(el, "valores"), "trib"), "gIBSCBS")
    _sub(g, "CST", grupo.cst)
    _sub(g, "cClassTrib", grupo.c_class_trib)


def _obra_xml(serv, obra: Obra) -> None:
    el = _sub(serv, "obra")
    if obra.insc_imob_fisc is not None:
        _sub(el, "inscImobFisc", obra.insc_imob_fisc)
    if obra.c_obra is not None:
        _sub(el, "cObra", obra.c_obra)
    elif obra.c_cib is not None:
        _sub(el, "cCIB", obra.c_cib)
    else:
        end = _sub(el, "end")
        _sub(end, "CEP", obra.endereco.cep)
        _sub(end, "xLgr", obra.endereco.logradouro)
        _sub(end, "nro", obra.endereco.numero)
        if obra.endereco.complemento is not None:
            _sub(end, "xCpl", obra.endereco.complemento)
        _sub(end, "xBairro", obra.endereco.bairro)


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
