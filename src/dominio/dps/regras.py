"""Regras e tabelas da DPS usadas pelo modelo e por outros módulos (T-043, saíram de src/dps.py).

Os códigos vêm dos anexos oficiais em docs/referencia/gov-docs/; cada tabela cita a regra.
"""

from __future__ import annotations

import re
from datetime import date

# TSString: sem espaço nas pontas nem quebra de linha, só caracteres de U+0020 a U+00FF.
TSSTRING = re.compile("[!-ÿ](?:[ -ÿ]*[!-ÿ])?")


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
# regApTribSN: 1 = federais e municipal pelo SN; 2 e 3 = ISSQN por fora (T-023).
APURACAO_PELO_SN = 1
# Série da DPS de aplicativo próprio (Anexo I v1.01, E0010; DEC-019).
SERIE_MIN, SERIE_MAX = 1, 49999

# Campos opcionais das notas atuais (T-018, DEC-023).
_FONE = re.compile(r"[0-9]{6,20}")  # TSTelefone
EMAIL_MAX = 80  # TSEmail
# E0148: "estrutura de e-mail". Conferência simples: algo@dominio.tld, sem espaços.
_EMAIL = re.compile(r"[^@\s]+@[^@\s.]+(\.[^@\s.]+)+")


def fone_valido(fone: object) -> bool:
    return isinstance(fone, str) and _FONE.fullmatch(fone) is not None


def email_valido(email: object) -> bool:
    return (
        isinstance(email, str) and len(email) <= EMAIL_MAX and _EMAIL.fullmatch(email) is not None
    )


# Grupo de obra (T-020, DEC-047). Anexo I v1.01, E0370: estes subitens exigem o grupo;
# E0372: os demais o proíbem, exceto o 99.01.01.
CODIGOS_DE_OBRA = frozenset([
    "070201", "070202", "070401", "070501", "070502", "070601", "070602",
    "070701", "070801", "071701", "071901", "141403", "141404",
])  # fmt: skip

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

# Substituição (T-031). Anexo I v1.01, grupo infDPS/subst: o XSD (TSCodJustSubst) pede o
# código com dois dígitos, embora o Anexo I diga tamanho 1 (docs/SOURCES.md).
OUTROS = 99
MOTIVOS_SUBSTITUICAO = (1, 2, 3, 4, 5, OUTROS)
