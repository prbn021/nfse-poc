"""DPS: modelo, regras e tabelas, XML (T-043; antes, tudo em `src/dps.py`).

O pacote expõe a mesma interface pública do módulo antigo, inclusive `NS`, `VERSAO` e
`validar_xml`, que agora moram em `src/dominio/xsd.py` (DEC-078).
"""

from src.dominio.dps.modelo import (
    Dps,
    EnderecoObra,
    IbsCbs,
    Obra,
    PisCofins,
    Prestador,
    Servico,
    Substituicao,
    Tomador,
    Valores,
    gerar_id,
)
from src.dominio.dps.regras import (
    APURACAO_PELO_SN,
    C_IND_OP_IMOVEL,
    C_IND_OP_NFSE,
    CODIGOS_DE_OBRA,
    CODIGOS_DE_OBRA_SEM_IMOVEL,
    IBSCBS_OBRIGATORIO_DESDE,
    IBSCBS_PERMITIDO_DESDE,
    ME_EPP,
    MEI,
    MOTIVOS_SUBSTITUICAO,
    NAO_OPTANTE,
    OUTROS,
    SERIE_MAX,
    SERIE_MIN,
    TSSTRING,
    email_valido,
    fone_valido,
    texto_tsstring,
)
from src.dominio.dps.xml import localizar_xsd_dps, para_xml
from src.dominio.xsd import NS, VERSAO, validar_xml

__all__ = [
    "APURACAO_PELO_SN",
    "CODIGOS_DE_OBRA",
    "CODIGOS_DE_OBRA_SEM_IMOVEL",
    "C_IND_OP_IMOVEL",
    "C_IND_OP_NFSE",
    "IBSCBS_OBRIGATORIO_DESDE",
    "IBSCBS_PERMITIDO_DESDE",
    "MEI",
    "ME_EPP",
    "MOTIVOS_SUBSTITUICAO",
    "NAO_OPTANTE",
    "NS",
    "OUTROS",
    "SERIE_MAX",
    "SERIE_MIN",
    "TSSTRING",
    "VERSAO",
    "Dps",
    "EnderecoObra",
    "IbsCbs",
    "Obra",
    "PisCofins",
    "Prestador",
    "Servico",
    "Substituicao",
    "Tomador",
    "Valores",
    "email_valido",
    "fone_valido",
    "gerar_id",
    "localizar_xsd_dps",
    "para_xml",
    "texto_tsstring",
    "validar_xml",
]
