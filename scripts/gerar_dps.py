"""Gera uma DPS de exemplo, salva em out/ e valida contra a cópia local dos XSDs oficiais.

Os dados do prestador vêm do emitente escolhido com --emitente (padrão: o exemplo fictício).
O percentual de pTotTribSN da competência vem de --p-tot-trib-sn (padrão fictício, Q-18).
"""

import argparse
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import carregar_config
from src.dps import (
    Dps,
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
from src.xsd import preparar_copia_local

BRT = timezone(timedelta(hours=-3))
P_TOT_TRIB_SN_FICTICIO = Decimal("6.00")


def dps_exemplo(
    tp_amb: int, emitente: Emitente, p_tot_trib_sn: Decimal = P_TOT_TRIB_SN_FICTICIO
) -> Dps:
    # Tomador, serviço e valores são FICTÍCIOS; o prestador é o emitente recebido.
    # Perfil mais comum da carteira: ME/EPP pelo Simples, tomador pessoa física (DEC-013).
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
            c_trib_nac="010101",
            c_trib_mun="001",
            descricao="Desenvolvimento de software sob encomenda",
        ),
        valores=Valores(
            v_serv=Decimal("100.00"),
            p_tot_trib_sn=p_tot_trib_sn,
            # Perfil da nota real do primeiro emitente: sem incidência, sem retenção (T-018).
            pis_cofins=PisCofins(cst="08", tp_ret_pis_cofins=0),
        ),
    )


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
    args = parser.parse_args(argv)
    try:
        emitente = carregar_emitente(args.emitente)
    except ValueError as erro:
        parser.error(str(erro))

    cfg = carregar_config()
    try:
        dps = dps_exemplo(cfg.tp_amb, emitente, _decimal(args.p_tot_trib_sn))
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
    xsd = localizar_xsd_dps(preparar_copia_local(cfg.xsd_dir))
    erros = validar_xml(xml, xsd)
    if erros:
        print(f"[X] Inválida contra {xsd.name}:")
        for e in erros:
            print("   -", e)
        return 1
    print(f"[OK] Válida contra {xsd.name} (cópia local em {xsd.parent})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
