"""Gera uma DPS de exemplo, salva em out/ e valida contra a cópia local dos XSDs oficiais.

Os dados do prestador vêm do emitente escolhido com --emitente (padrão: o exemplo fictício).
"""

import argparse
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import carregar_config
from src.dps import (
    Dps,
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


def dps_exemplo(tp_amb: int, emitente: Emitente) -> Dps:
    # Tomador, serviço e valores são FICTÍCIOS; o prestador é o emitente recebido.
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
            op_simp_nac=emitente.op_simp_nac,
            reg_esp_trib=emitente.reg_esp_trib,
        ),
        tomador=Tomador(nome="Cliente de Teste Ltda", cnpj="99888777000161"),
        servico=Servico(
            c_loc_prestacao="3304557",
            c_trib_nac="010101",
            descricao="Desenvolvimento de software sob encomenda",
        ),
        valores=Valores(v_serv=Decimal("100.00")),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--emitente",
        default=EXEMPLO,
        help="nome do arquivo em emitentes/, sem .toml (padrão: %(default)s, fictício)",
    )
    args = parser.parse_args(argv)
    try:
        emitente = carregar_emitente(args.emitente)
    except ValueError as erro:
        parser.error(str(erro))

    cfg = carregar_config()
    dps = dps_exemplo(cfg.tp_amb, emitente)
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
