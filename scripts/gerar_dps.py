"""Gera uma DPS de exemplo, salva em out/ e valida contra o pacote oficial de XSDs ativo.

Os dados do prestador vêm do emitente escolhido com --emitente (padrão: o exemplo fictício).
O percentual de pTotTribSN da competência vem de --p-tot-trib-sn (padrão fictício, Q-18).
Para um serviço de obra: --c-trib-nac com um código de obra e --obra-cno (T-020).
O grupo IBS/CBS leva --c-ind-op e --c-class-trib, e o serviço o NBS em --c-nbs (T-034; padrão
fictício do Anexo VIII).
"""

import argparse
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import carregar_config
from src.dominio.dps import (
    Dps,
    IbsCbs,
    Obra,
    PisCofins,
    Prestador,
    Servico,
    Tomador,
    Valores,
    localizar_xsd_dps,
    para_xml,
    validar_xml,
)
from src.emitente import EXEMPLO, Emitente, carregar_emitente

BRT = timezone(timedelta(hours=-3))
P_TOT_TRIB_SN_FICTICIO = Decimal("6.00")
C_TRIB_NAC_FICTICIO = "010101"
# Grupo IBS/CBS (T-034): a linha do Anexo VIII para o item 01.01 do serviço padrão.
C_IND_OP_FICTICIO = "100301"
C_CLASS_TRIB_FICTICIO = "000001"
C_NBS_FICTICIO = "115021000"  # 1.1502.10.00, exigido com o grupo (E0322)


def dps_exemplo(
    tp_amb: int,
    emitente: Emitente,
    p_tot_trib_sn: Decimal = P_TOT_TRIB_SN_FICTICIO,
    *,
    c_trib_nac: str = C_TRIB_NAC_FICTICIO,
    obra_cno: str | None = None,
    c_ind_op: str = C_IND_OP_FICTICIO,
    c_class_trib: str = C_CLASS_TRIB_FICTICIO,
    c_nbs: str = C_NBS_FICTICIO,
) -> Dps:
    # Tomador, serviço e valores são FICTÍCIOS; o prestador é o emitente recebido.
    # Perfil mais comum da carteira: ME/EPP pelo Simples, tomador pessoa física (DEC-013).
    # Com obra_cno, o serviço leva o grupo de obra com o CNO dado (T-020); o código de
    # tributação precisa ser de obra (E0370, E0372). O grupo IBS/CBS vai sempre: a
    # competência é a data de hoje, e desde 01/10/2026 ele é obrigatório (E0855).
    return Dps(
        tp_amb=tp_amb,
        c_loc_emi=emitente.municipio,
        serie=1,
        n_dps=1,
        d_compet=date.today(),
        dh_emi=datetime.now(BRT).replace(microsecond=0),
        prestador=Prestador(
            cnpj=emitente.cnpj,
            inscricao_municipal=emitente.inscricao_municipal,
            fone=emitente.fone,
            email=emitente.email,
            op_simp_nac=emitente.op_simp_nac,
            reg_esp_trib=emitente.reg_esp_trib,
            reg_ap_trib_sn=emitente.reg_ap_trib_sn,
        ),
        tomador=Tomador(nome="Cliente de Teste", cpf="12345678909"),
        servico=Servico(
            c_loc_prestacao="3304557",
            c_trib_nac=c_trib_nac,
            c_trib_mun="001",
            descricao="Desenvolvimento de software sob encomenda",
            obra=None if obra_cno is None else Obra(c_obra=obra_cno),
            c_nbs=c_nbs,
        ),
        valores=Valores(
            v_serv=Decimal("100.00"),
            p_tot_trib_sn=p_tot_trib_sn,
            # Perfil da nota real do primeiro emitente: sem incidência, sem retenção (T-018).
            pis_cofins=PisCofins(cst="08", tp_ret_pis_cofins=0),
        ),
        ibs_cbs=IbsCbs(c_ind_op=c_ind_op, c_class_trib=c_class_trib),
    )


def nbs(texto: str) -> str:
    """Código NBS como no Anexo VIII (1.1502.10.00) ou só os 9 dígitos."""
    return texto.replace(".", "")


def _decimal(texto: str) -> Decimal:
    try:
        return Decimal(texto)
    except InvalidOperation:
        raise ValueError(
            f"p_tot_trib_sn inválido: {texto!r} (use ponto decimal, ex.: 6.00)"
        ) from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--emitente",
        default=EXEMPLO,
        help="nome do arquivo em emitentes/, sem .toml (padrão: %(default)s, fictício)",
    )
    parser.add_argument(
        "--p-tot-trib-sn",
        default=str(P_TOT_TRIB_SN_FICTICIO),
        help="%% aproximado dos tributos do Simples na competência (padrão: %(default)s, fictício)",
    )
    parser.add_argument(
        "--c-trib-nac",
        default=C_TRIB_NAC_FICTICIO,
        help="código de tributação nacional, 6 dígitos (padrão: %(default)s, fictício)",
    )
    parser.add_argument(
        "--obra-cno",
        help="número da obra no CNO (ou CEI): põe o grupo de obra, exigido pelos códigos de "
        "obra (E0370); padrão: nenhum",
    )
    parser.add_argument(
        "--c-ind-op",
        default=C_IND_OP_FICTICIO,
        help="código indicador da operação do grupo IBS/CBS, 6 dígitos, do Anexo VII "
        "(padrão: %(default)s, fictício)",
    )
    parser.add_argument(
        "--c-class-trib",
        default=C_CLASS_TRIB_FICTICIO,
        help="classificação tributária do IBS e da CBS, 6 dígitos; o CST são os 3 primeiros "
        "(padrão: %(default)s, fictício)",
    )
    parser.add_argument(
        "--c-nbs",
        default=C_NBS_FICTICIO,
        help="código NBS do serviço, com ou sem pontos, exigido com o grupo IBS/CBS (E0322) "
        "(padrão: %(default)s, fictício)",
    )
    args = parser.parse_args(argv)
    try:
        emitente = carregar_emitente(args.emitente)
    except ValueError as erro:
        parser.error(str(erro))

    cfg = carregar_config()
    try:
        dps = dps_exemplo(
            cfg.tp_amb,
            emitente,
            _decimal(args.p_tot_trib_sn),
            c_trib_nac=args.c_trib_nac,
            obra_cno=args.obra_cno,
            c_ind_op=args.c_ind_op,
            c_class_trib=args.c_class_trib,
            c_nbs=nbs(args.c_nbs),
        )
    except ValueError as erro:
        parser.error(str(erro))
    xml = para_xml(dps)

    saida = Path("out")
    saida.mkdir(exist_ok=True)
    arq = saida / f"{dps.id}.xml"
    arq.write_bytes(xml)
    print(f"DPS gerada: {arq}\n{xml.decode()}\n")

    if not localizar_xsd_dps(cfg.xsd_dir):
        print(f"[!] XSD não encontrado em {cfg.xsd_dir}. Veja schemas/LEIAME.md.")
        return 2
    xsd = localizar_xsd_dps(cfg.xsd_dir)
    erros = validar_xml(xml, xsd)
    if erros:
        print(f"[X] Inválida contra {xsd.name}:")
        for e in erros:
            print("   -", e)
        return 1
    print(f"[OK] Válida contra {xsd.name} ({xsd.parent})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
