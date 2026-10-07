"""Gera uma DPS de exemplo, salva em out/ e valida contra o XSD oficial (se estiver em schemas/)."""
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import carregar_config
from src.dps import (Dps, Prestador, Servico, Tomador, Valores,
                     localizar_xsd_dps, para_xml, validar_xml)

BRT = timezone(timedelta(hours=-3))


def dps_exemplo(tp_amb: int) -> Dps:
    # Dados FICTÍCIOS. Troque pelos dados do prestador do certificado de testes.
    return Dps(
        tp_amb=tp_amb,
        c_loc_emi="3304557",                       # exemplo: IBGE do Rio de Janeiro
        serie=1,
        n_dps=1,
        d_compet=date.today(),
        dh_emi=datetime.now(BRT).replace(microsecond=0),
        prestador=Prestador(cnpj="11222333000181", inscricao_municipal="12345",
                            op_simp_nac=3),
        tomador=Tomador(nome="Cliente de Teste Ltda", cnpj="99888777000161"),
        servico=Servico(c_loc_prestacao="3304557", c_trib_nac="010101",
                        descricao="Desenvolvimento de software sob encomenda"),
        valores=Valores(v_serv=Decimal("100.00")),
    )


def main() -> int:
    cfg = carregar_config()
    dps = dps_exemplo(cfg.tp_amb)
    xml = para_xml(dps)

    saida = Path("out"); saida.mkdir(exist_ok=True)
    arq = saida / f"{dps.id}.xml"
    arq.write_bytes(xml)
    print(f"DPS gerada: {arq}\n{xml.decode()}\n")

    xsd = localizar_xsd_dps(cfg.xsd_dir)
    if not xsd:
        print(f"[!] XSD não encontrado em {cfg.xsd_dir}. Veja schemas/LEIAME.md.")
        return 2
    erros = validar_xml(xml, xsd)
    if erros:
        print(f"[X] Inválida contra {xsd.name}:")
        for e in erros:
            print("   -", e)
        return 1
    print(f"[OK] Válida contra {xsd.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
