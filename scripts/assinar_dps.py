"""Assina a DPS de exemplo com o certificado do emitente, confere e empacota em GZip+Base64.

Script manual (T-005): abre o certificado real do emitente indicado, sem rede. Salva em out/
a DPS assinada (.xml) e a mesma DPS em GZip+Base64 (.b64). Confirma que a chave assina e que
a assinatura confere localmente; só a transmissão confirma que a SEFIN a aceita (T-007).
Não mostra senha, chave nem conteúdo do certificado (INV-05).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gerar_dps import P_TOT_TRIB_SN_FICTICIO, _decimal, dps_exemplo

from src.assinatura import assinar_dps, conferir_assinatura
from src.certificado import carregar_certificado
from src.codec import codificar, decodificar
from src.config import carregar_config
from src.dominio.dps import localizar_xsd_dps, para_xml, validar_xml
from src.emitente import PASTA, carregar_emitente


def main(argv: list[str] | None = None, pasta: Path = PASTA, saida: Path = Path("out")) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--emitente", required=True, help="nome do arquivo em emitentes/, sem .toml"
    )
    parser.add_argument(
        "--p-tot-trib-sn",
        default=str(P_TOT_TRIB_SN_FICTICIO),
        help="%% aproximado dos tributos do Simples na competência (padrão: %(default)s, fictício)",
    )
    args = parser.parse_args(argv)

    cfg = carregar_config()
    try:
        emitente = carregar_emitente(args.emitente, pasta)
        cert = carregar_certificado(emitente.cert_path, emitente.cert_senha)
        dps = dps_exemplo(cfg.tp_amb, emitente, _decimal(args.p_tot_trib_sn))
        assinada = assinar_dps(para_xml(dps), cert)
        conferir_assinatura(assinada, cert.certificado)
    except ValueError as erro:
        print(f"[X] {erro}", file=sys.stderr)
        return 1

    if not localizar_xsd_dps(cfg.xsd_dir):
        print(f"[!] XSD não encontrado em {cfg.xsd_dir}. Veja schemas/LEIAME.md.", file=sys.stderr)
        return 2
    xsd = localizar_xsd_dps(cfg.xsd_dir)
    erros = validar_xml(assinada, xsd)
    if erros:
        print(f"[X] DPS assinada inválida contra {xsd.name}:", file=sys.stderr)
        for e in erros:
            print("   -", e, file=sys.stderr)
        return 1

    empacotada = codificar(assinada)
    if decodificar(empacotada) != assinada:
        print("[X] GZip+Base64 não devolveu a mesma DPS", file=sys.stderr)
        return 1

    saida.mkdir(parents=True, exist_ok=True)
    xml_arq = saida / f"{dps.id}-assinada.xml"
    b64_arq = saida / f"{dps.id}-assinada.b64"
    xml_arq.write_bytes(assinada)
    b64_arq.write_text(empacotada, encoding="ascii")

    print(f"[OK] Assinatura conferida com o certificado de {cert.titular}")
    print(f"[OK] Válida contra {xsd.name} ({xsd.parent})")
    print(f"[OK] GZip+Base64 com {len(empacotada)} caracteres; decodificado, é a mesma DPS")
    print(f"DPS assinada: {xml_arq}")
    print(f"GZip+Base64:  {b64_arq}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
